"""Tenant-safe access to organization operational context."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.organizations.models import OrganizationOperationalProfile


async def get_operational_profile(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
) -> OrganizationOperationalProfile | None:
    """Prefer a site profile, then fall back to the tenant-wide profile."""

    profile = await session.scalar(
        select(OrganizationOperationalProfile).where(
            OrganizationOperationalProfile.organization_id == organization_id,
            OrganizationOperationalProfile.site_id == site_id,
        )
    )
    if profile is not None:
        return profile
    return await session.scalar(
        select(OrganizationOperationalProfile).where(
            OrganizationOperationalProfile.organization_id == organization_id,
            OrganizationOperationalProfile.site_id.is_(None),
        )
    )
