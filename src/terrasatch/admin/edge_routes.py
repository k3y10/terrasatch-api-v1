"""Session-protected browser flow for approving TerraSatch Edge pairings."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Awaitable, Callable
from html import escape
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.security import csrf_token_is_valid, issue_csrf_token
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

    csrf = issue_csrf_token(request.session)
    org_options = "".join(
        f'<option value="{escape(str(org.id))}" {"selected" if str(org.id) == selected_org else ""}>{escape(org.name)}</option>'
        for org in organizations
    )
    site_options = "".join(
        f'<option value="{escape(str(site.id))}">{escape(site.name)}</option>'
        for site in sites
    )
    message = ""
    if approved:
        message = f'<div class="ok">Device pairing <strong>{escape(approved)}</strong> approved. The Edge node can now claim its credential.</div>'
    elif error:
        message = f'<div class="error">{escape(error)}</div>'

    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TerraSatch Edge Pairing</title>
<style>
body{{font-family:system-ui;background:#0d1117;color:#e6edf3;max-width:760px;margin:48px auto;padding:0 20px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:24px;margin:18px 0}}
label{{display:block;margin:14px 0 6px;color:#b7c0ca}} input,select,button{{width:100%;box-sizing:border-box;padding:12px;border-radius:8px;border:1px solid #3b4652;background:#0d1117;color:#fff}}
button{{background:#d86f2d;border:0;font-weight:700;cursor:pointer;margin-top:16px}} a{{color:#f0a66f}} .ok{{padding:12px;background:#15351f;border-radius:8px}} .error{{padding:12px;background:#421d1d;border-radius:8px}}
code{{font-size:1.2rem;letter-spacing:.08em}}
</style></head>
<body><p><a href="/admin">← Admin</a></p><h1>Approve TerraSatch Edge</h1>
<p>Match the code shown by the field computer, choose its organization and site, then approve it.</p>
{message}
<div class="card">
<form method="get" action="/admin/edge/pair">
<label>Pairing code</label><input name="code" value="{escape(code)}" placeholder="ABCD-2345" required>
<label>Organization</label><select name="organization" required><option value="">Select organization</option>{org_options}</select>
<button type="submit">Load sites</button>
</form></div>
<div class="card">
<form method="post" action="/admin/edge/pair">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="organization" value="{escape(selected_org)}">
<label>Pairing code</label><input name="code" value="{escape(code)}" required>
<label>Site</label><select name="site_id" required><option value="">Select site</option>{site_options}</select>
<button type="submit" {"disabled" if not sites else ""}>Approve device</button>
</form></div></body></html>""")


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
