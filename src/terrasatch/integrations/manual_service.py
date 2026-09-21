"""Manual service-account credential setup for supported non-OAuth providers."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable
from terrasatch.identity.models import MembershipRole

from .crypto import encrypt_payload
from .models import IntegrationConnection, IntegrationCredential, IntegrationStatus
from .operations import (
    probe_aws_s3_bucket,
    probe_cloudflare_r2_bucket,
    query_caltopo_map,
    query_caltopo_team,
    query_snowflake,
    validate_generic_webhook_url,
    validate_public_webhook_destination,
    validate_teams_workflow_url,
)
from .service import get_connection_for_management

MANUAL_CREDENTIAL_PROVIDERS = {
    "aws_s3",
    "caltopo",
    "cloudflare_r2",
    "microsoft_teams",
    "snowflake",
    "webhook",
}


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
        map_ids = configuration.get("map_ids")
        if isinstance(map_ids, list) and map_ids:
            first_map = map_ids[0]
            if not isinstance(first_map, str):
                raise InvalidConfiguration("CalTopo map configuration is invalid")
            await query_caltopo_map(
                credentials,
                map_id=first_map,
                since=0,
            )
        else:
            await query_caltopo_team(
                credentials,
                team_id=team_id,
                since=int(datetime.now(UTC).timestamp() * 1000) - 60_000,
            )
        return f"CalTopo Team {team_id}", team_id

    if provider == "aws_s3":
        region = configuration.get("region")
        bucket = configuration.get("bucket")
        if not isinstance(region, str) or not isinstance(bucket, str):
            raise InvalidConfiguration("Amazon S3 configuration is missing")
        result = await probe_aws_s3_bucket(
            credentials,
            region=region,
            bucket=bucket,
        )
        host = result.metadata.get("endpoint_host")
        return (
            f"Amazon S3 · {bucket}",
            str(host) if host else bucket,
        )

    if provider == "cloudflare_r2":
        endpoint_url = configuration.get("endpoint_url")
        bucket = configuration.get("bucket")
        if not isinstance(endpoint_url, str) or not isinstance(bucket, str):
            raise InvalidConfiguration("Cloudflare R2 configuration is missing")
        result = await probe_cloudflare_r2_bucket(
            credentials,
            endpoint_url=endpoint_url,
            bucket=bucket,
        )
        host = result.metadata.get("endpoint_host")
        return (
            f"Cloudflare R2 · {bucket}",
            str(host) if host else bucket,
        )

    if provider == "microsoft_teams":
        raw_url = credentials.get("webhook_url")
        if not isinstance(raw_url, str):
            raise InvalidConfiguration("Microsoft Teams webhook credential is missing")
        url = validate_teams_workflow_url(raw_url)
        await validate_public_webhook_destination(
            url,
            label="Microsoft Teams",
        )
        host = urlsplit(url).hostname
        return "Microsoft Teams Workflows", host

    if provider == "webhook":
        raw_url = credentials.get("webhook_url")
        if not isinstance(raw_url, str):
            raise InvalidConfiguration("Webhook credential is missing")
        url = validate_generic_webhook_url(raw_url)
        await validate_public_webhook_destination(url, label="Generic")
        host = urlsplit(url).hostname
        return f"Webhook · {host}", host

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
    elif connection.provider == "snowflake":
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
    elif connection.provider == "aws_s3":
        supplied = set(values)
        allowed = (
            {"access_key_id", "secret_access_key"},
            {"access_key_id", "secret_access_key", "session_token"},
        )
        if supplied not in allowed:
            raise InvalidConfiguration(
                "Amazon S3 credentials require access_key_id, secret_access_key, "
                "and optional session_token"
            )
        credential_payload = {
            "access_key_id": _required_string(
                values,
                "access_key_id",
                max_length=255,
            ),
            "secret_access_key": _required_string(
                values,
                "secret_access_key",
                max_length=4096,
            ),
        }
        if "session_token" in values:
            credential_payload["session_token"] = _required_string(
                values,
                "session_token",
                max_length=8192,
            )
    elif connection.provider == "cloudflare_r2":
        expected = {"access_key_id", "secret_access_key"}
        if set(values) != expected:
            raise InvalidConfiguration(
                "Cloudflare R2 credentials require access_key_id and secret_access_key"
            )
        credential_payload = {
            "access_key_id": _required_string(
                values,
                "access_key_id",
                max_length=255,
            ),
            "secret_access_key": _required_string(
                values,
                "secret_access_key",
                max_length=4096,
            ),
        }
    elif connection.provider == "microsoft_teams":
        expected = {"webhook_url"}
        if set(values) != expected:
            raise InvalidConfiguration(
                "Microsoft Teams credentials require webhook_url"
            )
        credential_payload = {
            "webhook_url": _required_string(values, "webhook_url", max_length=8192)
        }
    else:
        supplied = set(values)
        if supplied not in ({"webhook_url"}, {"webhook_url", "signing_secret"}):
            raise InvalidConfiguration(
                "Webhook credentials require webhook_url and optional signing_secret"
            )
        credential_payload = {
            "webhook_url": _required_string(values, "webhook_url", max_length=8192)
        }
        if "signing_secret" in values:
            credential_payload["signing_secret"] = _required_string(
                values,
                "signing_secret",
                max_length=4096,
            )

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
