"""Tenant-safe identity services used by the public control plane."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.api.schemas import TeamCreateRequest, TeamUpdateRequest
from terrasatch.errors import ResourceConflict, ResourceNotFound
from terrasatch.identity.models import Site, Team


async def _enabled_site_for_org(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
) -> Site:
    site = await session.scalar(
        select(Site).where(
            Site.id == site_id,
            Site.organization_id == organization_id,
            Site.enabled.is_(True),
        )
    )
    if site is None:
        raise ResourceNotFound("Site was not found in the authenticated organization")
    return site


async def create_team(
    session: AsyncSession,
    *,
    organization_id: UUID,
    payload: TeamCreateRequest,
) -> Team:
    if payload.site_id is not None:
        await _enabled_site_for_org(
            session,
            organization_id=organization_id,
            site_id=payload.site_id,
        )
    name = payload.name.strip()
    existing = await session.scalar(
        select(Team).where(Team.organization_id == organization_id, Team.name == name)
    )
    if existing is not None:
        raise ResourceConflict(f"Team '{name}' already exists")
    team = Team(
        organization_id=organization_id,
        site_id=payload.site_id,
        name=name,
    )
    session.add(team)
    await session.flush()
    return team


async def list_teams(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID | None = None,
    enabled: bool | None = None,
) -> list[Team]:
    query = select(Team).where(Team.organization_id == organization_id)
    if site_id is not None:
        query = query.where(Team.site_id == site_id)
    if enabled is not None:
        query = query.where(Team.enabled.is_(enabled))
    return list(await session.scalars(query.order_by(Team.name)))


async def get_team(
    session: AsyncSession,
    *,
    organization_id: UUID,
    team_id: UUID,
) -> Team:
    team = await session.scalar(
        select(Team).where(Team.id == team_id, Team.organization_id == organization_id)
    )
    if team is None:
        raise ResourceNotFound("Team was not found in the authenticated organization")
    return team


async def update_team(
    session: AsyncSession,
    *,
    organization_id: UUID,
    team_id: UUID,
    payload: TeamUpdateRequest,
) -> Team:
    team = await get_team(session, organization_id=organization_id, team_id=team_id)

    if "name" in payload.model_fields_set and payload.name is not None:
        name = payload.name.strip()
        existing = await session.scalar(
            select(Team).where(
                Team.organization_id == organization_id,
                Team.name == name,
                Team.id != team.id,
            )
        )
        if existing is not None:
            raise ResourceConflict(f"Team '{name}' already exists")
        team.name = name

    if "site_id" in payload.model_fields_set:
        if payload.site_id is not None:
            await _enabled_site_for_org(
                session,
                organization_id=organization_id,
                site_id=payload.site_id,
            )
        team.site_id = payload.site_id

    if payload.enabled is not None:
        team.enabled = payload.enabled

    await session.flush()
    return team
