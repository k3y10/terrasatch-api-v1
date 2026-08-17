"""Session-protected administrative browser interface."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.commands_v2 import run_admin_command
from terrasatch.admin.device_status import device_status_payload, fleet_summary
from terrasatch.admin.security import csrf_token_is_valid, issue_csrf_token, verify_admin_password
from terrasatch.admin.ui import render_login, render_one_time_key
from terrasatch.admin.ui_v2 import render_dashboard
from terrasatch.auth.service import issue_api_key, list_api_keys
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.edge.service import list_devices
from terrasatch.errors import TerraSatchError
from terrasatch.observability.quality import build_quality_report
from terrasatch.organizations.service import (
    create_organization,
    create_site,
    list_organizations,
    list_sites,
    resolve_organization,
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
    edge_devices: list[object] = []
    api_keys: list[object] = []
    selected_name = "No organization selected"
    selected_slug = ""
    selected_enabled = False

    if selected_organization:
        try:
            organization, sites = await _run_database(
                settings,
                lambda session: list_sites(
                    session,
                    organization_selector=selected_organization,
                    enabled=None,
                ),
            )
            selected_name = organization.name
            selected_slug = organization.slug
            selected_enabled = organization.enabled
            edge_devices = await _run_database(
                settings,
                lambda session: list_devices(
                    session,
                    organization_id=organization.id,
                ),
            )
            api_keys = await _run_database(
                settings,
                lambda session: list_api_keys(
                    session,
                    organization_selector=str(organization.id),
                ),
            )
        except Exception as error:
            logger.warning("admin.tenant_context_failed", error_type=type(error).__name__)
            error_message = "Tenant context is unavailable for the selected organization."

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
            selected_slug=selected_slug,
            selected_enabled=selected_enabled,
            sites=sites,
            edge_devices=edge_devices,
            api_keys=api_keys,
            csrf_token=csrf_token,
            error_message=error_message,
        )
    )


@router.get("/admin/fleet-status", include_in_schema=False, response_model=None)
async def admin_fleet_status(
    request: Request,
    organization: str = "",
) -> JSONResponse:
    """Return current registered Edge heartbeat/capability state to an admin session."""

    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)

    async def load_fleet(session: AsyncSession) -> list[dict[str, object]]:
        if organization:
            organizations = [await resolve_organization(session, organization)]
        else:
            organizations = await list_organizations(session)

        now = datetime.now(UTC)
        devices: list[dict[str, object]] = []
        for item in organizations:
            for device in await list_devices(session, organization_id=item.id):
                payload = device_status_payload(device, now=now)
                payload["organization_id"] = str(item.id)
                payload["organization_name"] = item.name
                devices.append(payload)
        return devices

    devices = await _run_database(settings, load_fleet)
    return JSONResponse(
        {
            "ok": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": fleet_summary(devices),
            "devices": devices,
        }
    )


@router.post("/admin/command", include_in_schema=False, response_model=None)
async def admin_command(
    request: Request,
    command: Annotated[str, Form()],
    organization: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)
    _verify_csrf(request, csrf_token)
    try:
        result = await _run_database(
            settings,
            lambda session: run_admin_command(
                session,
                command=command,
                selected_organization=organization or None,
            ),
        )
    except TerraSatchError as error:
        return JSONResponse(
            {"ok": False, "lines": [f"error: {error.message}"]},
            status_code=error.status_code,
        )
    except Exception as error:
        logger.exception("admin.command_failed", error_type=type(error).__name__)
        return JSONResponse(
            {"ok": False, "lines": ["error: command failed"]},
            status_code=500,
        )
    return JSONResponse({"ok": True, "lines": result.lines, "redirect": result.redirect})


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
        return RedirectResponse(f"/admin?error={quote(error.message)}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(f"/admin?organization={organization.id}", status_code=status.HTTP_303_SEE_OTHER)


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
    return RedirectResponse(f"/admin?organization={organization}", status_code=status.HTTP_303_SEE_OTHER)


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
