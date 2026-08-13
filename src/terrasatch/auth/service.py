"""Service API-key issuance and persistence."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.auth.api_keys import GeneratedApiKey, generate_api_key
from terrasatch.auth.models import ApiKey
from terrasatch.auth.scopes import validate_api_scopes
from terrasatch.config import Settings
from terrasatch.errors import ResourceNotFound
from terrasatch.organizations.service import resolve_organization


async def issue_api_key(
    session: AsyncSession,
    *,
    settings: Settings,
    name: str,
    scopes: Iterable[str],
    organization_selector: str | None = None,
) -> tuple[ApiKey, GeneratedApiKey]:
    """Persist a tenant-scoped digest and return its raw token only to the caller."""

    organization = await resolve_organization(session, organization_selector)
    normalized_scopes = validate_api_scopes(set(scopes))
    generated = generate_api_key(environment=settings.environment.value)
    api_key = ApiKey(
        organization_id=organization.id,
        name=name.strip(),
        key_prefix=generated.key_prefix,
        secret_hash=generated.secret_hash,
        scopes=normalized_scopes,
    )
    session.add(api_key)
    await session.flush()
    return api_key, generated


async def list_api_keys(
    session: AsyncSession,
    *,
    organization_selector: str | None = None,
) -> list[ApiKey]:
    """List non-secret credential metadata for the resolved organization only."""

    organization = await resolve_organization(session, organization_selector)
    return list(
        await session.scalars(
            select(ApiKey)
            .where(ApiKey.organization_id == organization.id)
            .order_by(ApiKey.created_at.desc())
        )
    )


async def revoke_api_key(
    session: AsyncSession,
    *,
    api_key_id: UUID,
    organization_selector: str | None = None,
) -> ApiKey:
    """Revoke a credential only if it belongs to the resolved organization."""

    organization = await resolve_organization(session, organization_selector)
    api_key = await session.scalar(
        select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.organization_id == organization.id)
    )
    if api_key is None:
        raise ResourceNotFound("API key was not found in the selected organization")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)
        await session.flush()
    return api_key
