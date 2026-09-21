"""Authorization and lifecycle helpers for integration connections."""

from __future__ import annotations

import re
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.errors import (
    InvalidConfiguration,
    ProviderUnavailable,
    ResourceConflict,
    ResourceNotFound,
    TenantAccessDenied,
)
from terrasatch.identity.access import role_allows
from terrasatch.identity.models import MembershipRole, Team

from .catalog import PROVIDERS, provider_support_status
from .models import (
    IntegrationConnection,
    IntegrationGrant,
    IntegrationScope,
    IntegrationStatus,
)
from .operations import (
    validate_arcgis_feature_layer_url,
    validate_aws_region,
    validate_r2_endpoint_url,
    validate_s3_bucket_name,
)

_SENSITIVE_KEY_PARTS = (
    "secret",
    "token",
    "password",
    "credential",
    "api_key",
    "apikey",
    "private_key",
)
_EMAIL_ADDRESS = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}"
    r"[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)

_ALLOWED_CONFIGURATION_KEYS: dict[str, set[str]] = {
    "google_drive": {"folder_id"},
    "microsoft_365": {"folder_path"},
    "cloudflare_r2": {"endpoint_url", "bucket", "prefix"},
    "aws_s3": {"region", "bucket", "prefix"},
    "email": {"recipients", "subject"},
    "snowflake": {"account_host", "warehouse", "database", "schema", "role"},
    "esri_arcgis": {"feature_layer_urls"},
    "caltopo": {"caltopo_team_id", "map_ids"},
}


def _validate_configuration(provider_key: str, configuration: dict[str, object]) -> None:
    allowed = _ALLOWED_CONFIGURATION_KEYS.get(provider_key, set())
    unexpected = sorted(set(configuration) - allowed)
    if unexpected:
        raise InvalidConfiguration(
            f"Unsupported configuration fields for {provider_key}: {', '.join(unexpected)}"
        )
    if "folder_id" in configuration:
        folder_id = configuration["folder_id"]
        if not isinstance(folder_id, str) or not folder_id.strip() or len(folder_id) > 512:
            raise InvalidConfiguration("Google Drive folder_id must be a non-empty string")

    if provider_key == "microsoft_365":
        folder_path = configuration.get("folder_path")
        if folder_path is not None:
            if not isinstance(folder_path, str) or len(folder_path) > 512:
                raise InvalidConfiguration("Microsoft folder_path must be a string")
            clean_path = "/".join(
                segment.strip()
                for segment in folder_path.replace("\\", "/").split("/")
                if segment.strip()
            )
            if ".." in clean_path.split("/"):
                raise InvalidConfiguration("Microsoft folder_path cannot contain '..'")
            configuration["folder_path"] = clean_path

    if provider_key == "cloudflare_r2":
        endpoint_url = configuration.get("endpoint_url")
        bucket = configuration.get("bucket")
        prefix = configuration.get("prefix", "")
        if not isinstance(endpoint_url, str):
            raise InvalidConfiguration("Cloudflare R2 endpoint_url is required")
        configuration["endpoint_url"] = validate_r2_endpoint_url(endpoint_url)
        if not isinstance(bucket, str):
            raise InvalidConfiguration("Cloudflare R2 bucket is required")
        configuration["bucket"] = validate_s3_bucket_name(bucket)
        if not isinstance(prefix, str) or len(prefix) > 512:
            raise InvalidConfiguration("Cloudflare R2 prefix must be a string")
        clean_prefix = "/".join(
            segment.strip()
            for segment in prefix.replace("\\", "/").split("/")
            if segment.strip()
        )
        if ".." in clean_prefix.split("/"):
            raise InvalidConfiguration("Cloudflare R2 prefix cannot contain '..'")
        configuration["prefix"] = clean_prefix

    if provider_key == "aws_s3":
        region = configuration.get("region")
        bucket = configuration.get("bucket")
        prefix = configuration.get("prefix", "")
        if not isinstance(region, str):
            raise InvalidConfiguration("Amazon S3 region is required")
        configuration["region"] = validate_aws_region(region)
        if not isinstance(bucket, str):
            raise InvalidConfiguration("Amazon S3 bucket is required")
        configuration["bucket"] = validate_s3_bucket_name(bucket)
        if not isinstance(prefix, str) or len(prefix) > 512:
            raise InvalidConfiguration("Amazon S3 prefix must be a string")
        clean_prefix = "/".join(
            segment.strip()
            for segment in prefix.replace("\\", "/").split("/")
            if segment.strip()
        )
        if ".." in clean_prefix.split("/"):
            raise InvalidConfiguration("Amazon S3 prefix cannot contain '..'")
        configuration["prefix"] = clean_prefix

    if provider_key == "email":
        recipients = configuration.get("recipients")
        subject = configuration.get("subject", "TerraSatch operational notification")
        if not isinstance(recipients, list) or not 1 <= len(recipients) <= 10:
            raise InvalidConfiguration(
                "Email recipients must be a list containing between 1 and 10 addresses"
            )
        normalized_recipients: list[str] = []
        for recipient in recipients:
            if (
                not isinstance(recipient, str)
                or len(recipient.strip()) > 320
                or not _EMAIL_ADDRESS.fullmatch(recipient.strip())
            ):
                raise InvalidConfiguration("Email recipients contains an invalid address")
            normalized_recipients.append(recipient.strip().casefold())
        if len(set(normalized_recipients)) != len(normalized_recipients):
            raise InvalidConfiguration("Email recipients cannot contain duplicates")
        if (
            not isinstance(subject, str)
            or not subject.strip()
            or len(subject.strip()) > 160
            or "\n" in subject
            or "\r" in subject
        ):
            raise InvalidConfiguration("Email subject must be a single-line string")
        configuration["recipients"] = normalized_recipients
        configuration["subject"] = " ".join(subject.split())

    if provider_key == "snowflake":
        account_host = configuration.get("account_host")
        if not isinstance(account_host, str):
            raise InvalidConfiguration("Snowflake account_host is required")
        account_host = account_host.strip().casefold()
        if (
            not account_host.endswith(".snowflakecomputing.com")
            or "://" in account_host
            or "/" in account_host
            or len(account_host) > 255
        ):
            raise InvalidConfiguration(
                "Snowflake account_host must be a snowflakecomputing.com hostname"
            )
        configuration["account_host"] = account_host
        for field in ("warehouse", "database", "schema", "role"):
            value = configuration.get(field)
            if value is not None:
                if not isinstance(value, str) or not value.strip() or len(value) > 255:
                    raise InvalidConfiguration(f"Snowflake {field} must be a short string")
                configuration[field] = value.strip()

    if provider_key == "caltopo":
        team_id = configuration.get("caltopo_team_id")
        if (
            not isinstance(team_id, str)
            or len(team_id.strip()) != 6
            or not team_id.strip().isalnum()
        ):
            raise InvalidConfiguration("CalTopo caltopo_team_id must be 6 alphanumeric characters")
        configuration["caltopo_team_id"] = team_id.strip()
        map_ids = configuration.get("map_ids", [])
        if not isinstance(map_ids, list) or len(map_ids) > 50:
            raise InvalidConfiguration("CalTopo map_ids must be a list of at most 50 IDs")
        normalized_maps: list[str] = []
        for map_id in map_ids:
            if (
                not isinstance(map_id, str)
                or not 4 <= len(map_id.strip()) <= 32
                or not map_id.strip().isalnum()
            ):
                raise InvalidConfiguration("CalTopo map_ids contains an invalid map ID")
            normalized_maps.append(map_id.strip())
        if len(set(normalized_maps)) != len(normalized_maps):
            raise InvalidConfiguration("CalTopo map_ids cannot contain duplicates")
        configuration["map_ids"] = normalized_maps

    if provider_key == "esri_arcgis":
        raw_layers = configuration.get("feature_layer_urls")
        if not isinstance(raw_layers, list) or not 1 <= len(raw_layers) <= 20:
            raise InvalidConfiguration(
                "ArcGIS requires between 1 and 20 approved feature_layer_urls"
            )
        normalized_layers: list[str] = []
        for raw_layer in raw_layers:
            if not isinstance(raw_layer, str):
                raise InvalidConfiguration("ArcGIS feature_layer_urls must contain strings")
            normalized_layers.append(validate_arcgis_feature_layer_url(raw_layer))
        if len(set(normalized_layers)) != len(normalized_layers):
            raise InvalidConfiguration("ArcGIS feature_layer_urls cannot contain duplicates")
        configuration["feature_layer_urls"] = normalized_layers


def _assert_non_secret_configuration(value: object, *, path: str = "configuration") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                raise InvalidConfiguration(
                    f"{path} cannot contain credentials or secrets; "
                    "provider credentials are stored server-side"
                )
            _assert_non_secret_configuration(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_non_secret_configuration(nested, path=f"{path}[{index}]")


async def _validated_team(
    session: AsyncSession, *, organization_id: UUID, team_id: UUID | None
) -> Team | None:
    if team_id is None:
        return None
    team = await session.scalar(
        select(Team).where(
            Team.id == team_id,
            Team.organization_id == organization_id,
            Team.enabled.is_(True),
        )
    )
    if team is None:
        raise ResourceNotFound("Integration team was not found in this organization")
    return team


def can_manage_scope(*, role: MembershipRole, scope: IntegrationScope) -> bool:
    if scope == IntegrationScope.USER:
        return True
    return role_allows(role, MembershipRole.ADMIN)


async def create_connection_request(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    provider_key: str,
    scope: IntegrationScope,
    team_id: UUID | None,
    display_name: str | None,
    configuration: dict[str, object],
) -> IntegrationConnection:
    provider = PROVIDERS.get(provider_key)
    if provider is None:
        raise ResourceNotFound("Integration provider was not found")
    if scope.value not in provider["scopes"]:
        raise InvalidConfiguration(f"{provider['name']} does not support {scope.value} scope")
    if provider["setup_status"] == "managed":
        raise InvalidConfiguration(
            f"{provider['name']} is managed by TerraSatch and is not added here"
        )
    support_status = provider_support_status(provider_key)
    if support_status in {"coming_soon", "partner_required"}:
        label = "partner access required" if support_status == "partner_required" else "coming soon"
        raise InvalidConfiguration(
            f"{provider['name']} is {label} and cannot be connected yet"
        )
    if provider["auth"] == "platform":
        if (
            provider_key != "email"
            or settings is None
            or not settings.integration_email_is_configured
        ):
            raise ProviderUnavailable(
                f"{provider['name']} platform delivery is not configured"
            )

    if not can_manage_scope(role=role, scope=scope):
        raise TenantAccessDenied(
            "Administrator access is required for team or organization integrations"
        )

    team = await _validated_team(
        session,
        organization_id=organization_id,
        team_id=team_id if scope == IntegrationScope.TEAM else None,
    )
    if scope == IntegrationScope.TEAM and team is None:
        raise InvalidConfiguration("Team scope requires a team")
    if scope != IntegrationScope.TEAM and team_id is not None:
        raise InvalidConfiguration("team_id is only valid for team-scoped integrations")

    _validate_configuration(provider_key, configuration)
    _assert_non_secret_configuration(configuration)

    owner_user_id = user_id if scope == IntegrationScope.USER else None
    duplicate_query = select(IntegrationConnection).where(
        IntegrationConnection.organization_id == organization_id,
        IntegrationConnection.provider == provider_key,
        IntegrationConnection.scope_type == scope.value,
        IntegrationConnection.status != IntegrationStatus.REVOKED.value,
    )
    if scope == IntegrationScope.USER:
        duplicate_query = duplicate_query.where(IntegrationConnection.owner_user_id == user_id)
    elif scope == IntegrationScope.TEAM:
        duplicate_query = duplicate_query.where(IntegrationConnection.team_id == team.id)
    else:
        duplicate_query = duplicate_query.where(
            IntegrationConnection.owner_user_id.is_(None),
            IntegrationConnection.team_id.is_(None),
        )
    if await session.scalar(duplicate_query) is not None:
        raise ResourceConflict(f"{provider['name']} already has an active {scope.value} connection")

    normalized_display_name = " ".join((display_name or provider["name"]).split())
    if not normalized_display_name:
        normalized_display_name = provider["name"]

    connection = IntegrationConnection(
        organization_id=organization_id,
        provider=provider_key,
        scope_type=scope.value,
        team_id=team.id if team is not None else None,
        owner_user_id=owner_user_id,
        created_by_user_id=user_id,
        display_name=normalized_display_name[:255],
        status=(
            IntegrationStatus.CONNECTED.value
            if provider["auth"] == "platform"
            else IntegrationStatus.REQUESTED.value
        ),
        configuration=dict(configuration),
        enabled=True,
        provider_account_label=(
            "TerraSatch Resend"
            if provider_key == "email"
            else None
        ),
        provider_account_id=("resend" if provider_key == "email" else None),
    )
    session.add(connection)
    await session.flush()

    subject_id = (
        str(user_id)
        if scope == IntegrationScope.USER
        else str(team.id)
        if scope == IntegrationScope.TEAM and team is not None
        else str(organization_id)
    )
    capabilities = list(provider["capabilities"])
    session.add_all(
        [
            IntegrationGrant(
                organization_id=organization_id,
                connection_id=connection.id,
                subject_type=scope.value,
                subject_id=subject_id,
                capabilities=capabilities,
                created_by_user_id=user_id,
                enabled=True,
            ),
            IntegrationGrant(
                organization_id=organization_id,
                connection_id=connection.id,
                subject_type="agent",
                subject_id="satchy",
                capabilities=capabilities,
                created_by_user_id=user_id,
                enabled=True,
            ),
        ]
    )
    await session.flush()
    return connection


async def list_visible_connections(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
) -> list[IntegrationConnection]:
    """
    Return connection metadata visible to this member.

    Team membership is not yet represented in portal identity, so team-scoped connection
    metadata remains administrator-only instead of being exposed to every organization member.
    """

    visible_scope = or_(
        IntegrationConnection.scope_type == IntegrationScope.ORGANIZATION.value,
        (
            (IntegrationConnection.scope_type == IntegrationScope.USER.value)
            & (IntegrationConnection.owner_user_id == user_id)
        ),
    )
    if role_allows(role, MembershipRole.ADMIN):
        visible_scope = or_(
            visible_scope,
            IntegrationConnection.scope_type == IntegrationScope.TEAM.value,
        )
    return list(
        await session.scalars(
            select(IntegrationConnection)
            .where(
                IntegrationConnection.organization_id == organization_id,
                visible_scope,
            )
            .order_by(IntegrationConnection.created_at.desc())
        )
    )


async def get_connection_for_management(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    connection_id: UUID,
    for_update: bool = False,
) -> IntegrationConnection:
    query = select(IntegrationConnection).where(
        IntegrationConnection.id == connection_id,
        IntegrationConnection.organization_id == organization_id,
    )
    if for_update:
        query = query.with_for_update()
    connection = await session.scalar(query)
    if connection is None:
        raise ResourceNotFound("Integration connection was not found")
    scope = IntegrationScope(connection.scope_type)
    if scope == IntegrationScope.USER:
        if connection.owner_user_id != user_id:
            raise ResourceNotFound("Integration connection was not found")
    elif not role_allows(role, MembershipRole.ADMIN):
        raise TenantAccessDenied("Administrator access is required to manage this integration")
    return connection


async def revoke_connection(
    session: AsyncSession,
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

    connection.status = IntegrationStatus.REVOKED.value
    connection.enabled = False
    connection.credential_ref = None
    await session.flush()
    return connection


def connection_payload(connection: IntegrationConnection) -> dict[str, object]:
    provider = PROVIDERS.get(connection.provider)
    return {
        "id": str(connection.id),
        "provider": connection.provider,
        "provider_name": provider["name"] if provider else connection.provider,
        "scope": connection.scope_type,
        "team_id": str(connection.team_id) if connection.team_id else None,
        "owner_user_id": str(connection.owner_user_id) if connection.owner_user_id else None,
        "display_name": connection.display_name,
        "status": connection.status,
        "configuration": dict(connection.configuration or {}),
        "provider_account_label": connection.provider_account_label,
        "provider_account_id": connection.provider_account_id,
        "last_synced_at": connection.last_synced_at,
        "last_error": connection.last_error,
        "enabled": connection.enabled,
        "created_at": connection.created_at,
    }
