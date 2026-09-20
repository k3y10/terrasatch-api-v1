"""Authorization and lifecycle helpers for integration connections."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.errors import InvalidConfiguration, ResourceConflict, ResourceNotFound, TenantAccessDenied
from terrasatch.identity.access import role_allows
from terrasatch.identity.models import MembershipRole, Team

from .catalog import PROVIDERS
from .models import IntegrationConnection, IntegrationScope, IntegrationStatus

_SENSITIVE_KEY_PARTS = ("secret", "token", "password", "credential", "api_key", "apikey", "private_key")
_ALLOWED_CONFIGURATION_KEYS: dict[str, set[str]] = {
    "google_drive": {"folder_id"},
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


def _assert_non_secret_configuration(value: object, *, path: str = "configuration") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                raise InvalidConfiguration(
                    f"{path} cannot contain credentials or secrets; provider credentials are stored server-side"
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
        raise InvalidConfiguration(f"{provider['name']} is managed by TerraSatch and is not added here")
    if not can_manage_scope(role=role, scope=scope):
        raise TenantAccessDenied("Administrator access is required for team or organization integrations")

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
        status=IntegrationStatus.REQUESTED.value,
        configuration=dict(configuration),
        enabled=True,
    )
    session.add(connection)
    await session.flush()
    return connection


async def list_visible_connections(
    session: AsyncSession, *, organization_id: UUID, user_id: UUID
) -> list[IntegrationConnection]:
    return list(
        await session.scalars(
            select(IntegrationConnection)
            .where(
                IntegrationConnection.organization_id == organization_id,
                or_(
                    IntegrationConnection.scope_type != IntegrationScope.USER.value,
                    IntegrationConnection.owner_user_id == user_id,
                ),
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
        if connection.owner_user_id != user_id and not role_allows(role, MembershipRole.ADMIN):
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
