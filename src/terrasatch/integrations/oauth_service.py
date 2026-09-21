"""Single-use OAuth orchestration and encrypted provider credential lifecycle."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.errors import AuthenticationFailed, ProviderUnavailable, TerraSatchError
from terrasatch.identity.models import MembershipRole

from .adapters import get_adapter, token_is_expiring
from .crypto import decrypt_payload, encrypt_payload
from .manual_service import (
    MANUAL_CREDENTIAL_PROVIDERS,
    probe_manual_credentials,
)
from .models import (
    IntegrationConnection,
    IntegrationCredential,
    IntegrationOAuthState,
    IntegrationStatus,
)
from .operations import query_geojson_features, query_ogc_features, query_stac_items
from .service import get_connection_for_management, revoke_connection


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def workspace_return_url(
    settings: Settings,
    *,
    connection: IntegrationConnection | None,
    success: bool,
    reason: str | None = None,
) -> str:
    parts = urlsplit(str(settings.integration_return_url))
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["view"] = "Integrations"
    query["integration"] = "connected" if success else "error"
    if connection is not None:
        query["provider"] = connection.provider
        query["connection_id"] = str(connection.id)
    if reason:
        query["reason"] = reason[:80]
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


async def begin_authorization(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    connection_id: UUID,
) -> tuple[IntegrationConnection, str, datetime]:
    if not settings.integration_secret_store_is_configured:
        raise ProviderUnavailable(
            "Integration credential storage is not configured"
        )
    connection = await get_connection_for_management(
        session,
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        connection_id=connection_id,
        for_update=True,
    )
    if connection.status == IntegrationStatus.REVOKED.value:
        raise ProviderUnavailable("Revoked integration requests cannot be authorized")

    adapter = get_adapter(connection.provider, settings)
    state = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.integration_oauth_state_ttl_minutes
    )
    session.add(
        IntegrationOAuthState(
            organization_id=organization_id,
            connection_id=connection.id,
            user_id=user_id,
            provider=connection.provider,
            state_hash=_state_hash(state),
            expires_at=expires_at,
        )
    )
    connection.status = IntegrationStatus.AWAITING_AUTHORIZATION.value
    connection.last_error = None
    await session.flush()
    return connection, adapter.authorization_url(state=state), expires_at


async def _credential_for_connection(
    session: AsyncSession,
    *,
    organization_id: UUID,
    connection_id: UUID,
) -> IntegrationCredential | None:
    return await session.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.organization_id == organization_id,
            IntegrationCredential.connection_id == connection_id,
        )
    )


async def _save_credentials(
    session: AsyncSession,
    settings: Settings,
    *,
    connection: IntegrationConnection,
    payload: dict[str, object],
) -> IntegrationCredential:
    credential = await _credential_for_connection(
        session,
        organization_id=connection.organization_id,
        connection_id=connection.id,
    )
    if credential is None:
        credential = IntegrationCredential(
            organization_id=connection.organization_id,
            connection_id=connection.id,
            key_id=settings.integration_encryption_key_id,
            encrypted_payload="",
        )
        session.add(credential)
        await session.flush()

    credential.key_id = settings.integration_encryption_key_id
    credential.encrypted_payload = encrypt_payload(settings, payload)
    connection.credential_ref = f"database:{credential.id}"
    await session.flush()
    return credential


async def complete_authorization(
    session: AsyncSession,
    settings: Settings,
    *,
    provider: str,
    state: str,
    code: str | None,
    provider_error: str | None,
) -> tuple[IntegrationConnection, bool, str | None]:
    oauth_state = await session.scalar(
        select(IntegrationOAuthState)
        .where(
            IntegrationOAuthState.provider == provider,
            IntegrationOAuthState.state_hash == _state_hash(state),
        )
        .with_for_update()
    )
    now = datetime.now(UTC)
    if oauth_state is None or oauth_state.consumed_at is not None:
        raise AuthenticationFailed("OAuth state is invalid or expired")

    expires_at = oauth_state.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise AuthenticationFailed("OAuth state is invalid or expired")

    oauth_state.consumed_at = now
    connection = await session.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.id == oauth_state.connection_id,
            IntegrationConnection.organization_id == oauth_state.organization_id,
            IntegrationConnection.provider == provider,
        )
        .with_for_update()
    )
    if connection is None:
        raise AuthenticationFailed("OAuth connection no longer exists")

    if provider_error:
        reason = provider_error.replace(" ", "_")[:80]
        connection.status = IntegrationStatus.ERROR.value
        connection.last_error = (
            f"Provider authorization was not completed ({reason})"
        )
        await session.flush()
        return connection, False, reason

    if not code:
        connection.status = IntegrationStatus.ERROR.value
        connection.last_error = "Provider authorization returned no code"
        await session.flush()
        return connection, False, "missing_code"

    try:
        result = await get_adapter(provider, settings).exchange_code(code=code)
        await _save_credentials(
            session,
            settings,
            connection=connection,
            payload=result.credentials,
        )
    except TerraSatchError as error:
        connection.status = IntegrationStatus.ERROR.value
        connection.last_error = error.message[:1000]
        await session.flush()
        return connection, False, error.code

    connection.provider_account_label = result.account_label
    connection.provider_account_id = result.account_id
    connection.status = IntegrationStatus.CONNECTED.value
    connection.last_error = None
    connection.last_synced_at = now
    connection.enabled = True
    await session.flush()
    return connection, True, None


async def active_credentials(
    session: AsyncSession,
    settings: Settings,
    *,
    connection: IntegrationConnection,
) -> tuple[dict[str, object], IntegrationCredential]:
    credential = await _credential_for_connection(
        session,
        organization_id=connection.organization_id,
        connection_id=connection.id,
    )
    if credential is None:
        raise ProviderUnavailable(
            "Integration credentials are unavailable; reconnect the provider"
        )

    payload = decrypt_payload(settings, credential.encrypted_payload)
    if token_is_expiring(payload):
        payload = await get_adapter(connection.provider, settings).refresh(payload)
        credential.key_id = settings.integration_encryption_key_id
        credential.encrypted_payload = encrypt_payload(settings, payload)
        await session.flush()
    return payload, credential


async def probe_connection(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    connection_id: UUID,
) -> IntegrationConnection:
    connection = await get_connection_for_management(
        session,
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        connection_id=connection_id,
        for_update=True,
    )
    if connection.status != IntegrationStatus.CONNECTED.value:
        raise ProviderUnavailable("Only connected integrations can be tested")

    try:
        if connection.provider == "email":
            if not settings.integration_email_is_configured:
                raise ProviderUnavailable(
                    "Operational email delivery is not configured"
                )
            label, account_id = "TerraSatch Resend", "resend"
        elif connection.provider == "geojson":
            configuration = dict(connection.configuration or {})
            endpoint_url = configuration.get("endpoint_url")
            if not isinstance(endpoint_url, str):
                raise ProviderUnavailable("GeoJSON endpoint is not configured")
            result = await query_geojson_features(
                endpoint_url=endpoint_url,
                max_features=1,
            )
            source_host = result.metadata.get("source_host")
            label = f"GeoJSON · {source_host}" if source_host else "GeoJSON"
            account_id = str(source_host) if source_host else None
        elif connection.provider == "ogc_api_features":
            configuration = dict(connection.configuration or {})
            base_url = configuration.get("base_url")
            collection_ids = configuration.get("collection_ids")
            if (
                not isinstance(base_url, str)
                or not isinstance(collection_ids, list)
                or not collection_ids
                or not isinstance(collection_ids[0], str)
            ):
                raise ProviderUnavailable("OGC API Features is not configured")
            result = await query_ogc_features(
                base_url=base_url,
                collection_id=collection_ids[0],
                limit=1,
            )
            source_host = result.metadata.get("source_host")
            label = f"OGC API · {source_host}" if source_host else "OGC API"
            account_id = str(source_host) if source_host else None
        elif connection.provider == "stac_api":
            configuration = dict(connection.configuration or {})
            base_url = configuration.get("base_url")
            collection_ids = configuration.get("collection_ids")
            if (
                not isinstance(base_url, str)
                or not isinstance(collection_ids, list)
                or not collection_ids
                or not isinstance(collection_ids[0], str)
            ):
                raise ProviderUnavailable("STAC API is not configured")
            result = await query_stac_items(
                base_url=base_url,
                collection_id=collection_ids[0],
                limit=1,
            )
            source_host = result.metadata.get("source_host")
            label = f"STAC API · {source_host}" if source_host else "STAC API"
            account_id = str(source_host) if source_host else None
        else:
            credentials, _ = await active_credentials(
                session,
                settings,
                connection=connection,
            )
            if connection.provider in MANUAL_CREDENTIAL_PROVIDERS:
                label, account_id = await probe_manual_credentials(
                    connection.provider,
                    credentials,
                    dict(connection.configuration or {}),
                )
            else:
                label, account_id = await get_adapter(
                    connection.provider,
                    settings,
                ).probe(credentials)
    except TerraSatchError as error:
        connection.status = IntegrationStatus.ERROR.value
        connection.last_error = error.message[:1000]
        await session.flush()
        return connection

    connection.provider_account_label = label or connection.provider_account_label
    connection.provider_account_id = account_id or connection.provider_account_id
    connection.last_synced_at = datetime.now(UTC)
    connection.last_error = None
    await session.flush()
    return connection


async def disconnect_connection(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    connection_id: UUID,
) -> IntegrationConnection:
    connection = await get_connection_for_management(
        session,
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        connection_id=connection_id,
        for_update=True,
    )
    credential = await _credential_for_connection(
        session,
        organization_id=organization_id,
        connection_id=connection.id,
    )
    if credential is not None:
        try:
            payload = decrypt_payload(settings, credential.encrypted_payload)
            if connection.provider not in MANUAL_CREDENTIAL_PROVIDERS:
                await get_adapter(connection.provider, settings).revoke(payload)
        except TerraSatchError as error:
            connection.status = IntegrationStatus.ERROR.value
            connection.last_error = error.message[:1000]
            await session.flush()
            return connection
        await session.delete(credential)

    return await revoke_connection(
        session,
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        connection_id=connection.id,
    )
