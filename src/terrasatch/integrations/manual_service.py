"""Manual service-account credential setup for supported non-OAuth providers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable
from terrasatch.identity.models import MembershipRole

from .crypto import encrypt_payload
from .models import IntegrationConnection, IntegrationCredential, IntegrationStatus
from .operations import query_caltopo_team, query_snowflake
from .service import get_connection_for_management

MANUAL_CREDENTIAL_PROVIDERS = {"caltopo", "snowflake"}


def _required_string(
    payload: dict[str, str],
    key: str,
    *,
    max_length: int = 8192,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise InvalidConfiguration(f"{key} is required")
    return value.strip()


async def probe_manual_credentials(
    provider: str,
    credentials: dict[str, object],
    configuration: dict[str, object],
) -> tuple[str | None, str | None]:
    if provider == "caltopo":
        team_id = configuration.get("caltopo_team_id")
        if not isinstance(team_id, str):
            raise InvalidConfiguration("CalTopo team configuration is missing")
        await query_caltopo_team(
            credentials,
            team_id=team_id,
            since=int(datetime.now(UTC).timestamp() * 1000) - 60_000,
        )
        return f"CalTopo Team {team_id}", team_id

    if provider == "snowflake":
        host = configuration.get("account_host")
        if not isinstance(host, str):
            raise InvalidConfiguration("Snowflake account_host is missing")
        await query_snowflake(
            credentials,
            account_host=host,
            statement="SELECT CURRENT_ACCOUNT()",
            warehouse=(
                configuration.get("warehouse")
                if isinstance(configuration.get("warehouse"), str)
                else None
            ),
            database=(
                configuration.get("database")
                if isinstance(configuration.get("database"), str)
                else None
            ),
            schema=(
                configuration.get("schema")
                if isinstance(configuration.get("schema"), str)
                else None
            ),
            role=(
                configuration.get("role")
                if isinstance(configuration.get("role"), str)
                else None
            ),
        )
        return host, host

    raise InvalidConfiguration("This integration does not use manual credentials")


async def bind_manual_credentials(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    connection_id: UUID,
    values: dict[str, str],
) -> IntegrationConnection:
    connection = await get_connection_for_management(
        session,
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        connection_id=connection_id,
        for_update=True,
    )
    if connection.provider not in MANUAL_CREDENTIAL_PROVIDERS:
        raise InvalidConfiguration("This integration uses provider authorization instead")
    if connection.status == IntegrationStatus.REVOKED.value:
        raise ProviderUnavailable("Revoked integrations cannot receive credentials")

    if connection.provider == "caltopo":
        expected = {"credential_id", "credential_secret"}
        if set(values) != expected:
            raise InvalidConfiguration(
                "CalTopo credentials require credential_id and credential_secret"
            )
        credential_payload: dict[str, object] = {
            "credential_id": _required_string(values, "credential_id", max_length=255),
            "credential_secret": _required_string(
                values,
                "credential_secret",
                max_length=4096,
            ),
        }
    else:
        expected = {"programmatic_access_token"}
        if set(values) != expected:
            raise InvalidConfiguration(
                "Snowflake credentials require programmatic_access_token"
            )
        credential_payload = {
            "programmatic_access_token": _required_string(
                values,
                "programmatic_access_token",
                max_length=8192,
            )
        }

    label, account_id = await probe_manual_credentials(
        connection.provider,
        credential_payload,
        dict(connection.configuration or {}),
    )

    credential = await session.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.organization_id == organization_id,
            IntegrationCredential.connection_id == connection.id,
        )
    )
    if credential is None:
        credential = IntegrationCredential(
            organization_id=organization_id,
            connection_id=connection.id,
            key_id=settings.integration_encryption_key_id,
            encrypted_payload="",
        )
        session.add(credential)
        await session.flush()

    credential.key_id = settings.integration_encryption_key_id
    credential.encrypted_payload = encrypt_payload(settings, credential_payload)
    connection.credential_ref = f"database:{credential.id}"
    connection.provider_account_label = label
    connection.provider_account_id = account_id
    connection.status = IntegrationStatus.CONNECTED.value
    connection.last_error = None
    connection.last_synced_at = datetime.now(UTC)
    connection.enabled = True
    await session.flush()
    return connection
