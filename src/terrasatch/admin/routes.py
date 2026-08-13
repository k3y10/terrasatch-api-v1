"""Session-protected administrative browser interface."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Awaitable, Callable
from html import escape
from typing import Annotated
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.security import csrf_token_is_valid, issue_csrf_token, verify_admin_password
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
        _dashboard_html(
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
    return HTMLResponse(_login_html(issue_csrf_token(request.session), failed=False))


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
        return HTMLResponse(_login_html(issue_csrf_token(request.session), failed=True), status_code=401)
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
    return HTMLResponse(_one_time_key_html(generated.token, organization))


def _login_html(csrf_token: str, *, failed: bool) -> str:
    error = "<p class=error>Invalid credentials.</p>" if failed else ""
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>TerraSatch API Administration</title>{_styles()}</head>
<body class=login><main><p class=eyebrow>TerraSatch API</p><h1>Administration</h1>
{error}<form method=post action=/admin/login><input type=hidden name=csrf_token value="{escape(csrf_token)}">
<label>Email<input required type=email name=email autocomplete=username></label>
<label>Password<input required type=password name=password autocomplete=current-password></label>
<button type=submit>Sign in</button></form></main></body></html>"""


def _dashboard_html(
    *,
    report_status: str,
    components: list[object],
    endpoints: list[object],
    errors: list[object],
    organizations: list[object],
    selected_organization: str,
    selected_name: str,
    sites: list[object],
    csrf_token: str,
    error_message: str | None,
) -> str:
    component_rows = "".join(
        f"<tr><td>{escape(component.name)}</td><td class={escape(component.status)}>{escape(component.status)}</td><td>{escape(component.detail or '')}</td></tr>"
        for component in components
    )
    endpoint_rows = "".join(
        f"<tr><td>{escape(endpoint.method)}</td><td><code>{escape(endpoint.path)}</code></td><td>{escape(endpoint.authorization)}</td><td>{escape(endpoint.summary or '')}</td></tr>"
        for endpoint in endpoints
    )
    error_rows = "".join(
        f"<tr><td>{error.http_status}</td><td><code>{escape(error.code)}</code></td><td>{escape(error.meaning)}</td></tr>"
        for error in errors
    )
    organization_options = "".join(
        f"<option value='{escape(str(organization.id))}'{' selected' if str(organization.id) == selected_organization else ''}>{escape(organization.name)}</option>"
        for organization in organizations
    )
    site_rows = "".join(f"<li>{escape(site.name)}</li>" for site in sites) or "<li>None</li>"
    error_box = f"<section class=error>{escape(error_message)}</section>" if error_message else ""
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>TerraSatch API Administration</title>{_styles()}</head><body>
<header><div><p class=eyebrow>TerraSatch API</p><h1>Operations Console</h1></div>
<form method=post action=/admin/logout><input type=hidden name=csrf_token value="{escape(csrf_token)}"><button class=quiet type=submit>Sign out</button></form></header>
<main><section class=overview><div><p class=label>Quality check</p><p class="result {escape(report_status)}">{escape(report_status.upper())}</p></div>
<p>Live API, database, Redis, and worker state. Hardware and provider checks appear only after their integrations are configured.</p></section>
{error_box}
<section><h2>Live Components</h2><table><thead><tr><th>Component</th><th>Status</th><th>Detail</th></tr></thead><tbody>{component_rows}</tbody></table></section>
<section class=columns><div><h2>Create Organization</h2><form method=post action=/admin/organizations><input type=hidden name=csrf_token value="{escape(csrf_token)}"><label>Name<input required name=name></label><button type=submit>Create</button></form></div>
<div><h2>Tenant Context</h2><form method=get action=/admin><label>Organization<select name=organization onchange="this.form.submit()"><option value="">Select organization</option>{organization_options}</select></label></form><p>{escape(selected_name)}</p><h3>Sites</h3><ul>{site_rows}</ul></div></section>
<section class=columns><div><h2>Create Site</h2><form method=post action=/admin/sites><input type=hidden name=csrf_token value="{escape(csrf_token)}"><input type=hidden name=organization value="{escape(selected_organization)}"><label>Name<input required name=name {'disabled' if not selected_organization else ''}></label><button type=submit {'disabled' if not selected_organization else ''}>Create</button></form></div>
<div><h2>Issue Server API Key</h2><form method=post action=/admin/api-keys><input type=hidden name=csrf_token value="{escape(csrf_token)}"><input type=hidden name=organization value="{escape(selected_organization)}"><label>Label<input required name=name {'disabled' if not selected_organization else ''}></label><label>Scopes<input name=scope value="read:events" {'disabled' if not selected_organization else ''}></label><button type=submit {'disabled' if not selected_organization else ''}>Issue key</button></form></div></section>
<section><h2>Implemented API Reference</h2><table><thead><tr><th>Method</th><th>Path</th><th>Authorization</th><th>Purpose</th></tr></thead><tbody>{endpoint_rows}</tbody></table></section>
<section><h2>Common Responses</h2><table><thead><tr><th>HTTP</th><th>Code</th><th>Meaning</th></tr></thead><tbody>{error_rows}</tbody></table></section>
</main></body></html>"""


def _one_time_key_html(token: str, organization: str) -> str:
    """Render a one-time credential outside session storage so it cannot enter a signed cookie."""

    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>TerraSatch API Key</title>{_styles()}</head><body class=login><main>
<p class=eyebrow>TerraSatch API</p><h1>New Server API Key</h1><section class=token>
<p>This token is shown only in this response. Store it in a server-side secret manager.</p>
<code>{escape(token)}</code></section><p><a href="/admin?organization={escape(organization)}">Return to operations console</a></p>
</main></body></html>"""


def _styles() -> str:
    return """<style>
    :root{--ink:#17222d;--canvas:#eef3f0;--paper:#fff;--line:#c9d4ce;--blue:#075985;--green:#166534;--red:#b42318;--muted:#5b6670}*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);font:16px Georgia,serif}header,main{max-width:1120px;margin:auto;padding:22px 28px}header{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line)}h1,h2,h3,p{margin-top:0}h1{font-size:29px;font-weight:500}h2{font-size:19px;font-weight:600}h3{font-size:15px}.eyebrow,.label{font:700 12px ui-monospace,monospace;color:var(--blue);letter-spacing:0}.overview{display:flex;gap:38px;align-items:center;border-bottom:2px solid var(--ink);padding:22px 0;margin-bottom:20px}.overview p:last-child{max-width:650px;color:var(--muted);margin:0}.result{font:700 30px ui-monospace,monospace;margin:0}.healthy,.pass{color:var(--green)}.unhealthy,.degraded,.error{color:var(--red)}section{background:var(--paper);border:1px solid var(--line);padding:20px;margin:18px 0}.columns{display:grid;grid-template-columns:1fr 1fr;gap:18px;background:none;border:0;padding:0}.columns>div{background:var(--paper);border:1px solid var(--line);padding:20px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:10px;border-top:1px solid var(--line);vertical-align:top}th{font:700 12px ui-monospace,monospace;color:var(--muted)}label{display:block;font:700 12px ui-monospace,monospace;margin:12px 0 5px}input,select{display:block;width:100%;padding:9px;border:1px solid #8da399;background:#fff;font:16px Georgia,serif}button{margin-top:12px;border:1px solid var(--blue);background:var(--blue);color:#fff;padding:9px 15px;font:700 13px ui-monospace,monospace;cursor:pointer}.quiet{background:transparent;color:var(--blue)}.login{display:grid;place-items:center;min-height:100vh}.login main{width:min(440px,100%);background:var(--paper);border:1px solid var(--line);padding:36px}.token{background:#fffbeb;border-color:#eab308}.token code{display:block;overflow-wrap:anywhere;margin-top:10px}@media(max-width:700px){header,.overview{display:block}.columns{grid-template-columns:1fr}header,main{padding:18px}table{display:block;overflow-x:auto}}
    </style>"""