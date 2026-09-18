"""Session-protected organization member portal."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.device_status import device_status_payload, fleet_summary
from terrasatch.admin.security import csrf_token_is_valid, issue_csrf_token
from terrasatch.billing.notifications import (
    get_account_email_context,
    get_billing_email_context,
)
from terrasatch.billing.outbox import enqueue_email
from terrasatch.billing.rate_limit import enforce_public_rate_limit
from terrasatch.billing.service import (
    get_stripe_customer_id,
    get_subscription_for_organization,
    recover_or_refresh_activation_for_email,
)
from terrasatch.billing.stripe_gateway import StripeGateway
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.edge.service import list_devices
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.identity.access import (
    authenticate_user,
    get_user_organization_access,
    list_user_access,
    role_allows,
    validate_browser_session,
)
from terrasatch.identity.models import MembershipRole
from terrasatch.identity.recovery import create_password_reset_intent, reset_password
from terrasatch.organizations.service import list_sites
from terrasatch.portal.ui import (
    render_portal,
    render_portal_forgot_password,
    render_portal_login,
    render_portal_resend_activation,
    render_portal_reset_password,
)

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


async def _require_user(
    request: Request,
    settings: Settings,
    *,
    session: AsyncSession | None = None,
) -> UUID:
    _enabled(settings)
    user_id = _portal_user_id(request)
    credential_version = request.session.get("portal_credential_version")
    if user_id is None or not isinstance(credential_version, int):
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Portal login required",
        )

    if session is None:
        user = await _run_database(
            settings,
            lambda database: validate_browser_session(
                database,
                user_id=user_id,
                credential_version=credential_version,
            ),
        )
    else:
        user = await validate_browser_session(
            session,
            user_id=user_id,
            credential_version=credential_version,
        )
    if user is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Portal login required",
        )
    return user_id


def _verify_csrf(request: Request, csrf_token: str) -> None:
    if not csrf_token_is_valid(request.session, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


async def _queue_password_reset(
    session: AsyncSession,
    *,
    email: str,
    settings: Settings,
) -> None:
    if not settings.billing_email_is_configured:
        return
    intent = await create_password_reset_intent(session, email=email, settings=settings)
    if intent is None:
        return
    context = await get_account_email_context(session, user_id=intent.user_id)
    if context is None:
        return
    await enqueue_email(
        session,
        event_id=f"account:password-reset:{intent.id}",
        kind="password_reset",
        context=context,
        password_reset_id=intent.id,
    )


async def _queue_activation_resend(
    session: AsyncSession,
    *,
    email: str,
    settings: Settings,
) -> None:
    if not settings.billing_email_is_configured:
        return
    recovered = await recover_or_refresh_activation_for_email(
        session,
        email=email,
        settings=settings,
    )
    if recovered is None:
        return
    token, organization_id = recovered
    context = await get_billing_email_context(session, organization_id=organization_id)
    if context is None:
        return
    await enqueue_email(
        session,
        event_id=f"account:activation-resend:{uuid4()}",
        kind="activation_resend",
        context=context,
        activation_token=token,
    )


@router.get(
    "/portal/login",
    response_class=HTMLResponse,
    include_in_schema=False,
    response_model=None,
)
async def portal_login_form(request: Request) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    if _portal_user_id(request) is not None:
        try:
            await _require_user(request, settings)
        except HTTPException:
            pass
        else:
            return RedirectResponse("/portal", status_code=status.HTTP_303_SEE_OTHER)
    notice = (
        "Password updated. Sign in with your new password."
        if request.query_params.get("reset") == "1"
        else None
    )
    return HTMLResponse(
        render_portal_login(
            issue_csrf_token(request.session),
            failed=False,
            notice=notice,
        )
    )


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
        return HTMLResponse(
            render_portal_login(issue_csrf_token(request.session), failed=True),
            status_code=401,
        )
    request.session.clear()
    request.session["portal_user_id"] = str(user.id)
    request.session["portal_credential_version"] = user.credential_version
    request.session["portal_email"] = user.email
    request.session["portal_display_name"] = user.display_name
    issue_csrf_token(request.session)
    return RedirectResponse("/portal", status_code=status.HTTP_303_SEE_OTHER)


@router.get(
    "/portal/forgot-password",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def portal_forgot_password_form(request: Request) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    return HTMLResponse(
        render_portal_forgot_password(
            issue_csrf_token(request.session),
            sent=False,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/portal/forgot-password",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def portal_forgot_password(
    request: Request,
    email: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    _verify_csrf(request, csrf_token)
    await enforce_public_rate_limit(
        settings,
        category="portal-password-reset",
        identifier=request.client.host if request.client else "unknown",
        limit=10,
        window=3600,
    )
    await _run_database(
        settings,
        lambda session: _queue_password_reset(
            session,
            email=email,
            settings=settings,
        ),
    )
    return HTMLResponse(
        render_portal_forgot_password(
            issue_csrf_token(request.session),
            sent=True,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/portal/resend-activation",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def portal_resend_activation_form(request: Request) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    return HTMLResponse(
        render_portal_resend_activation(
            issue_csrf_token(request.session),
            sent=False,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/portal/resend-activation",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def portal_resend_activation(
    request: Request,
    email: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    _verify_csrf(request, csrf_token)
    await enforce_public_rate_limit(
        settings,
        category="portal-activation-resend",
        identifier=request.client.host if request.client else "unknown",
        limit=10,
        window=3600,
    )
    await _run_database(
        settings,
        lambda session: _queue_activation_resend(
            session,
            email=email,
            settings=settings,
        ),
    )
    return HTMLResponse(
        render_portal_resend_activation(
            issue_csrf_token(request.session),
            sent=True,
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/portal/reset-password",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def portal_reset_password_form(request: Request) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    return HTMLResponse(
        render_portal_reset_password(issue_csrf_token(request.session)),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post(
    "/portal/reset-password",
    include_in_schema=False,
    response_model=None,
)
async def portal_reset_password(
    request: Request,
    token: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    _verify_csrf(request, csrf_token)
    if not token or password != confirm_password:
        return HTMLResponse(
            render_portal_reset_password(
                issue_csrf_token(request.session),
                error="The reset link is missing or the passwords do not match.",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )
    try:
        await _run_database(
            settings,
            lambda session: reset_password(
                session,
                token=token,
                password=password,
            ),
        )
    except (InvalidConfiguration, ResourceNotFound) as error:
        return HTMLResponse(
            render_portal_reset_password(
                issue_csrf_token(request.session),
                error=str(error),
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    request.session.clear()
    return RedirectResponse(
        "/portal/login?reset=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/portal/logout", include_in_schema=False)
async def portal_logout(
    request: Request,
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    _verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/portal/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get(
    "/portal",
    response_class=HTMLResponse,
    include_in_schema=False,
    response_model=None,
)
async def portal_dashboard(
    request: Request,
    organization: str = "",
) -> HTMLResponse | RedirectResponse:
    settings: Settings = request.app.state.settings
    _enabled(settings)
    try:
        user_id = await _require_user(request, settings)
    except HTTPException:
        return RedirectResponse("/portal/login", status_code=status.HTTP_303_SEE_OTHER)

    access = await _run_database(
        settings,
        lambda session: list_user_access(session, user_id=user_id),
    )
    if not access:
        request.session.clear()
        return RedirectResponse("/portal/login", status_code=status.HTTP_303_SEE_OTHER)

    remembered = str(request.session.get("portal_organization") or "")
    selector = organization or remembered
    selected = next((item for item in access if str(item.organization_id) == selector), access[0])
    request.session["portal_organization"] = str(selected.organization_id)

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
    subscription = await _run_database(
        settings,
        lambda session: get_subscription_for_organization(
            session,
            organization_id=selected.organization_id,
        ),
    )

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
            billing=subscription.model_dump(mode="json"),
            billing_manage_allowed=role_allows(selected.role, MembershipRole.ADMIN),
            csrf_token=issue_csrf_token(request.session),
        )
    )


@router.post("/portal/billing", include_in_schema=False, response_model=None)
async def portal_billing(
    request: Request,
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    """Open Stripe Customer Portal only for an authorized organization admin/owner."""

    settings: Settings = request.app.state.settings
    user_id = await _require_user(request, settings)
    _verify_csrf(request, csrf_token)
    try:
        organization_id = UUID(organization)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization") from error

    selected = await _run_database(
        settings,
        lambda session: get_user_organization_access(
            session,
            user_id=user_id,
            organization_id=organization_id,
        ),
    )
    if not role_allows(selected.role, MembershipRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin or owner access is required to manage billing",
        )
    customer_id = await _run_database(
        settings,
        lambda session: get_stripe_customer_id(
            session,
            organization_id=organization_id,
        ),
    )
    url = await StripeGateway(settings).create_customer_portal(stripe_customer_id=customer_id)
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/portal/fleet-status", include_in_schema=False, response_model=None)
async def portal_fleet_status(
    request: Request,
    organization: str = "",
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    user_id = await _require_user(request, settings)
    access = await _run_database(
        settings,
        lambda session: list_user_access(session, user_id=user_id),
    )
    if not access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No organization access")

    remembered = str(request.session.get("portal_organization") or "")
    selector = organization or remembered
    selected_access = next(
        (item for item in access if str(item.organization_id) == selector),
        access[0],
    )
    selected = await _run_database(
        settings,
        lambda session: get_user_organization_access(
            session,
            user_id=user_id,
            organization_id=selected_access.organization_id,
        ),
    )
    request.session["portal_organization"] = str(selected.organization_id)
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
