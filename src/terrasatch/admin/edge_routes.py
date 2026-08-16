"""Session-protected browser flow for approving TerraSatch Edge pairings."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.security import csrf_token_is_valid, issue_csrf_token
from terrasatch.admin.ui import render_edge_pair
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.edge.service import approve_pairing
from terrasatch.errors import TerraSatchError
from terrasatch.organizations.service import list_organizations, list_sites, resolve_organization

router = APIRouter(tags=["admin"])


async def _run_database[Result](
    settings: Settings,
    operation: Callable[[AsyncSession], Awaitable[Result]],
) -> Result:
    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        try:
            result = await operation(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


def _require_admin(request: Request, settings: Settings) -> None:
    if not settings.admin_is_configured:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin console is not configured")
    if request.session.get("admin_authenticated") is not True:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")


@router.get(
    "/admin/edge/pair",
    response_class=HTMLResponse,
    include_in_schema=False,
    response_model=None,
)
async def edge_pair_form(request: Request) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    if not settings.admin_is_configured:
        raise HTTPException(status_code=404, detail="Admin console is not configured")
    if request.session.get("admin_authenticated") is not True:
        return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    code = request.query_params.get("code", "")
    selected_org = request.query_params.get("organization", "")
    approved = request.query_params.get("approved")
    error = request.query_params.get("error")

    organizations = await _run_database(settings, list_organizations)
    sites: list[object] = []
    if selected_org:
        try:
            _organization, sites = await _run_database(
                settings,
                lambda session: list_sites(session, organization_selector=selected_org, enabled=True),
            )
        except TerraSatchError as exc:
            error = exc.message

    return HTMLResponse(
        render_edge_pair(
            code=code,
            selected_org=selected_org,
            approved=approved,
            error=error,
            organizations=organizations,
            sites=sites,
            csrf_token=issue_csrf_token(request.session),
        )
    )


@router.post("/admin/edge/pair", include_in_schema=False)
async def approve_edge_pairing(
    request: Request,
    code: Annotated[str, Form()],
    organization: Annotated[str, Form()],
    site_id: Annotated[UUID, Form()],
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_admin(request, settings)
    if not csrf_token_is_valid(request.session, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    try:
        async def operation(session: AsyncSession):
            org = await resolve_organization(session, organization)
            return await approve_pairing(
                session,
                user_code=code,
                organization_id=org.id,
                api_key_id=None,
                site_id=site_id,
            )
        pairing = await _run_database(settings, operation)
    except TerraSatchError as exc:
        return RedirectResponse(
            f"/admin/edge/pair?code={quote(code)}&organization={quote(organization)}&error={quote(exc.message)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        f"/admin/edge/pair?approved={quote(pairing.user_code)}&organization={quote(organization)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
