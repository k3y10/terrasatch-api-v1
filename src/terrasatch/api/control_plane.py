"""Tenant-safe JSON control-plane endpoints for sites, teams, and API keys."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.api.schemas import (
    ApiKeyCreateRequest,
    ApiKeyResponse,
    IssuedApiKeyResponse,
    SiteCreateRequest,
    SiteResponse,
    SiteUpdateRequest,
    TeamCreateRequest,
    TeamResponse,
    TeamUpdateRequest,
)
from terrasatch.auth.dependencies import Principal, require_scope
from terrasatch.auth.models import ApiKey
from terrasatch.auth.service import issue_api_key, list_api_keys, revoke_api_key
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.identity.models import Site, Team
from terrasatch.identity.service import create_team, get_team, list_teams, update_team
from terrasatch.organizations.service import create_site, get_site, list_sites, update_site

router = APIRouter(tags=["control-plane"])


async def _run_database[Result](
    settings: Settings,
    operation: Callable[[AsyncSession], Awaitable[Result]],
) -> Result:
    """Run one request-scoped database transaction."""

    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        try:
            result = await operation(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


def _site_response(site: Site) -> SiteResponse:
    return SiteResponse(
        id=site.id,
        organization_id=site.organization_id,
        name=site.name,
        slug=site.slug,
        enabled=site.enabled,
        created_at=site.created_at,
        updated_at=site.updated_at,
    )


def _team_response(team: Team) -> TeamResponse:
    return TeamResponse(
        id=team.id,
        organization_id=team.organization_id,
        site_id=team.site_id,
        name=team.name,
        enabled=team.enabled,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


def _api_key_response(api_key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id,
        organization_id=api_key.organization_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        revoked_at=api_key.revoked_at,
    )


@router.get("/sites", response_model=list[SiteResponse])
async def get_sites(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:sites"))],
    enabled: Annotated[bool | None, Query()] = None,
) -> list[SiteResponse]:
    """List sites only for the API key's server-derived organization."""

    _organization, sites = await _run_database(
        request.app.state.settings,
        lambda session: list_sites(
            session,
            organization_selector=str(principal.organization_id),
            enabled=enabled,
        ),
    )
    return [_site_response(site) for site in sites]


@router.post("/sites", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def post_site(
    payload: SiteCreateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:sites"))],
) -> SiteResponse:
    """Create a site in the authenticated key's organization."""

    site = await _run_database(
        request.app.state.settings,
        lambda session: create_site(
            session,
            name=payload.name,
            organization_selector=str(principal.organization_id),
        ),
    )
    return _site_response(site)


@router.get("/sites/{site_id}", response_model=SiteResponse)
async def get_site_by_id(
    site_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:sites"))],
) -> SiteResponse:
    site = await _run_database(
        request.app.state.settings,
        lambda session: get_site(
            session,
            organization_id=principal.organization_id,
            site_id=site_id,
        ),
    )
    return _site_response(site)


@router.patch("/sites/{site_id}", response_model=SiteResponse)
async def patch_site(
    site_id: UUID,
    payload: SiteUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:sites"))],
) -> SiteResponse:
    site = await _run_database(
        request.app.state.settings,
        lambda session: update_site(
            session,
            organization_id=principal.organization_id,
            site_id=site_id,
            payload=payload,
        ),
    )
    return _site_response(site)


@router.get("/teams", response_model=list[TeamResponse])
async def get_teams(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:teams"))],
    site_id: Annotated[UUID | None, Query()] = None,
    enabled: Annotated[bool | None, Query()] = None,
) -> list[TeamResponse]:
    teams = await _run_database(
        request.app.state.settings,
        lambda session: list_teams(
            session,
            organization_id=principal.organization_id,
            site_id=site_id,
            enabled=enabled,
        ),
    )
    return [_team_response(team) for team in teams]


@router.post("/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def post_team(
    payload: TeamCreateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:teams"))],
) -> TeamResponse:
    team = await _run_database(
        request.app.state.settings,
        lambda session: create_team(
            session,
            organization_id=principal.organization_id,
            payload=payload,
        ),
    )
    return _team_response(team)


@router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team_by_id(
    team_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:teams"))],
) -> TeamResponse:
    team = await _run_database(
        request.app.state.settings,
        lambda session: get_team(
            session,
            organization_id=principal.organization_id,
            team_id=team_id,
        ),
    )
    return _team_response(team)


@router.patch("/teams/{team_id}", response_model=TeamResponse)
async def patch_team(
    team_id: UUID,
    payload: TeamUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:teams"))],
) -> TeamResponse:
    team = await _run_database(
        request.app.state.settings,
        lambda session: update_team(
            session,
            organization_id=principal.organization_id,
            team_id=team_id,
            payload=payload,
        ),
    )
    return _team_response(team)


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def get_api_keys(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> list[ApiKeyResponse]:
    """List non-secret credential metadata for the key's organization."""

    keys = await _run_database(
        request.app.state.settings,
        lambda session: list_api_keys(
            session,
            organization_selector=str(principal.organization_id),
        ),
    )
    return [_api_key_response(api_key) for api_key in keys]


@router.post("/api-keys", response_model=IssuedApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def post_api_key(
    payload: ApiKeyCreateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> IssuedApiKeyResponse:
    """Issue a tenant-scoped service key and return its raw token exactly once."""

    api_key, generated = await _run_database(
        request.app.state.settings,
        lambda session: issue_api_key(
            session,
            settings=request.app.state.settings,
            name=payload.name,
            scopes=payload.scopes,
            organization_selector=str(principal.organization_id),
        ),
    )
    return IssuedApiKeyResponse(**_api_key_response(api_key).model_dump(), token=generated.token)


@router.post("/api-keys/{api_key_id}/revoke", response_model=ApiKeyResponse)
async def post_api_key_revoke(
    api_key_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> ApiKeyResponse:
    """Revoke a service key only if it belongs to the caller's organization."""

    api_key = await _run_database(
        request.app.state.settings,
        lambda session: revoke_api_key(
            session,
            api_key_id=api_key_id,
            organization_selector=str(principal.organization_id),
        ),
    )
    return _api_key_response(api_key)
