"""Session-protected organization member portal."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.device_status import device_status_payload, fleet_summary
from terrasatch.admin.security import csrf_token_is_valid, issue_csrf_token
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.edge.service import list_devices
from terrasatch.identity.access import (
    authenticate_user,
    get_user_organization_access,
    list_user_access,
)
from terrasatch.organizations.service import list_sites
from terrasatch.portal.ui import render_portal, render_portal_login

router = APIRouter(tags=["portal"])


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


def _enabled(settings: Settings) -> None:
    if settings.admin_session_secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal is not configured")


def _portal_user_id(request: Request) -> UUID | None:
    value = request.session.get("portal_user_id")
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _require_user(request: Request, settings: Settings) -> UUID:
    _enabled(settings)
    user_id = _portal_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Portal login required")
    return user_id


def _verify_csrf(request: Request, csrf_token: str) -> None:
    if not csrf_token_is_valid(request.session, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


@router.get("/portal/login", response_class=HTMLResponse, include_in_schema=False)
async def portal_login_form(request: Request) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    if _portal_user_id(request) is not None:
        return RedirectResponse("/portal", status_code=status.HTTP_303_SEE_OTHER)
    return HTMLResponse(render_portal_login(issue_csrf_token(request.session), failed=False))


@router.post("/portal/login", include_in_schema=False, response_model=None)
async def portal_login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    _verify_csrf(request, csrf_token)
    user = await _run_database(
        settings,
        lambda session: authenticate_user(session, email=email, password=password),
    )
    if user is None:
        return HTMLResponse(render_portal_login(issue_csrf_token(request.session), failed=True), status_code=401)
    request.session.clear()
    request.session["portal_user_id"] = str(user.id)
    request.session["portal_email"] = user.email
    request.session["portal_display_name"] = user.display_name
    issue_csrf_token(request.session)
    return RedirectResponse("/portal", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/portal/logout", include_in_schema=False)
async def portal_logout(
    request: Request,
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_user(request, settings)
    _verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/portal/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/portal", response_class=HTMLResponse, include_in_schema=False)
async def portal_dashboard(
    request: Request,
    organization: str = "",
) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    user_id = _portal_user_id(request)
    if user_id is None:
        return RedirectResponse("/portal/login", status_code=status.HTTP_303_SEE_OTHER)

    access = await _run_database(settings, lambda session: list_user_access(session, user_id=user_id))
    if not access:
        request.session.clear()
        return RedirectResponse("/portal/login", status_code=status.HTTP_303_SEE_OTHER)

    selected = next((item for item in access if str(item.organization_id) == organization), access[0])
    _, sites = await _run_database(
        settings,
        lambda session: list_sites(
            session,
            organization_selector=str(selected.organization_id),
            enabled=None,
        ),
    )
    edge_devices = await _run_database(
        settings,
        lambda session: list_devices(session, organization_id=selected.organization_id),
    )
    devices = [device_status_payload(device) for device in edge_devices]
    summary = fleet_summary(devices)

    return HTMLResponse(
        render_portal(
            display_name=str(request.session.get("portal_display_name") or "TerraSatch User"),
            email=str(request.session.get("portal_email") or ""),
            role=selected.role.value,
            access_options=[(str(item.organization_id), item.organization_name) for item in access],
            selected_organization=str(selected.organization_id),
            selected_name=selected.organization_name,
            sites=sites,
            devices=devices,
            summary=summary,
            csrf_token=issue_csrf_token(request.session),
        )
    )


@router.get("/portal/fleet-status", include_in_schema=False, response_model=None)
async def portal_fleet_status(
    request: Request,
    organization: str = "",
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    user_id = _require_user(request, settings)
    access = await _run_database(settings, lambda session: list_user_access(session, user_id=user_id))
    if not access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No organization access")

    selected_id = UUID(organization) if organization else access[0].organization_id
    selected = await _run_database(
        settings,
        lambda session: get_user_organization_access(
            session,
            user_id=user_id,
            organization_id=selected_id,
        ),
    )
    devices = await _run_database(
        settings,
        lambda session: list_devices(session, organization_id=selected.organization_id),
    )
    payloads = [device_status_payload(device) for device in devices]
    return JSONResponse(
        {
            "ok": True,
            "organization_id": str(selected.organization_id),
            "organization_name": selected.organization_name,
            "role": selected.role.value,
            "summary": fleet_summary(payloads),
            "devices": payloads,
        }
    )
