"""Tenant-safe, JSON control-plane endpoints for sites and API keys."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.api.schemas import (
    ApiKeyCreateRequest,
    ApiKeyResponse,
    IssuedApiKeyResponse,
    SiteCreateRequest,
    SiteResponse,
)
from terrasatch.auth.dependencies import Principal, require_scope
from terrasatch.auth.models import ApiKey
from terrasatch.auth.service import issue_api_key, list_api_keys, revoke_api_key
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.identity.models import Site
from terrasatch.organizations.service import create_site, list_sites

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
    principal: Annotated[Principal, Depends(require_scope("admin"))],
) -> list[SiteResponse]:
    """List sites only for the API key's server-derived organization."""

    _organization, sites = await _run_database(
        request.app.state.settings,
        lambda session: list_sites(session, organization_selector=str(principal.organization_id)),
    )
    return [_site_response(site) for site in sites]


@router.post("/sites", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def post_site(
    payload: SiteCreateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("admin"))],
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