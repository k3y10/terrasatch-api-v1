"""Session-protected administrative browser interface."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.security import csrf_token_is_valid, issue_csrf_token, verify_admin_password
from terrasatch.admin.ui import render_dashboard, render_login, render_one_time_key
from terrasatch.auth.service import issue_api_key
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.errors import TerraSatchError
from terrasatch.observability.quality import build_quality_report
from terrasatch.organizations.service import (
    create_organization,
    create_site,
    list_organizations,
    list_sites,
)

router = APIRouter(tags=["admin"])
logger = structlog.get_logger(__name__)


def _enabled(settings: Settings) -> None:
    if not settings.admin_is_configured:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin console is not configured",
        )


def _is_authenticated(request: Request) -> bool:
    return request.session.get("admin_authenticated") is True


def _redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)


def _require_authenticated(request: Request, settings: Settings) -> None:
    _enabled(settings)
    if not _is_authenticated(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")


def _verify_csrf(request: Request, csrf_token: str) -> None:
    if not csrf_token_is_valid(request.session, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


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


@router.get(
    "/admin",
    response_class=HTMLResponse,
    include_in_schema=False,
    response_model=None,
)
async def admin_dashboard(request: Request) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    if not _is_authenticated(request):
        return _redirect_to_login()
    report = await build_quality_report(settings)
    error_message = request.query_params.get("error")
    try:
        organizations = await _run_database(settings, list_organizations)
    except Exception as error:
        logger.warning("admin.organization_list_failed", error_type=type(error).__name__)
        organizations = []
        error_message = "Organization data is unavailable while the database is unhealthy."
    selected_organization = request.query_params.get("organization")
    sites: list[object] = []
    selected_name = "No organization selected"
    if selected_organization:
        try:
            organization, sites = await _run_database(
                settings,
                lambda session: list_sites(session, organization_selector=selected_organization),
            )
            selected_name = organization.name
        except Exception as error:
            logger.warning("admin.site_list_failed", error_type=type(error).__name__)
            error_message = "Site data is unavailable for the selected organization."
    csrf_token = issue_csrf_token(request.session)
    return HTMLResponse(
        render_dashboard(
            report_status=report.status,
            components=report.components,
            endpoints=report.endpoints,
            errors=report.common_errors,
            organizations=organizations,
            selected_organization=selected_organization or "",
            selected_name=selected_name,
            sites=sites,
            csrf_token=csrf_token,
            error_message=error_message,
        )
    )


@router.get(
    "/admin/login",
    response_class=HTMLResponse,
    include_in_schema=False,
    response_model=None,
)
async def admin_login_form(request: Request) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    if _is_authenticated(request):
        return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)
    return HTMLResponse(render_login(issue_csrf_token(request.session), failed=False))


@router.post("/admin/login", include_in_schema=False, response_model=None)
async def admin_login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    _verify_csrf(request, csrf_token)
    expected_hash = settings.admin_password_hash
    if (
        email.casefold() != (settings.admin_email or "").casefold()
        or expected_hash is None
        or not verify_admin_password(password, expected_hash.get_secret_value())
    ):
        return HTMLResponse(render_login(issue_csrf_token(request.session), failed=True), status_code=401)
    request.session.clear()
    request.session["admin_authenticated"] = True
    issue_csrf_token(request.session)
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/logout", include_in_schema=False)
async def admin_logout(request: Request, csrf_token: Annotated[str, Form()]) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)
    _verify_csrf(request, csrf_token)
    request.session.clear()
    return _redirect_to_login()


@router.post("/admin/organizations", include_in_schema=False)
async def admin_create_organization(
    request: Request,
    name: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)
    _verify_csrf(request, csrf_token)
    try:
        organization = await _run_database(settings, lambda session: create_organization(session, name=name))
    except TerraSatchError as error:
        return RedirectResponse(
            f"/admin?error={quote(error.message)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        f"/admin?organization={organization.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/sites", include_in_schema=False)
async def admin_create_site(
    request: Request,
    name: Annotated[str, Form()],
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)
    _verify_csrf(request, csrf_token)
    try:
        await _run_database(
            settings,
            lambda session: create_site(session, name=name, organization_selector=organization),
        )
    except TerraSatchError as error:
        return RedirectResponse(
            f"/admin?organization={organization}&error={quote(error.message)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        f"/admin?organization={organization}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/api-keys", include_in_schema=False, response_model=None)
async def admin_create_api_key(
    request: Request,
    name: Annotated[str, Form()],
    scope: Annotated[str, Form()],
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)
    _verify_csrf(request, csrf_token)
    scopes = [item.strip() for item in scope.split(",") if item.strip()]
    try:
        _, generated = await _run_database(
            settings,
            lambda session: issue_api_key(
                session,
                settings=settings,
                name=name,
                scopes=scopes or ["read:events"],
                organization_selector=organization,
            ),
        )
    except TerraSatchError as error:
        return RedirectResponse(
            f"/admin?organization={organization}&error={quote(error.message)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return HTMLResponse(render_one_time_key(generated.token, organization))
