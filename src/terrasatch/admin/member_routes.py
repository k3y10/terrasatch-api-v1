"""Superadmin routes for creating organization member browser accounts."""
# ruff: noqa: E501

from __future__ import annotations

from html import escape
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from terrasatch.admin.routes import _require_authenticated, _run_database, _verify_csrf
from terrasatch.admin.security import issue_csrf_token
from terrasatch.brand import SASQUATCH_ASSET_URL
from terrasatch.identity.access import (
    create_or_update_organization_member,
    list_organization_members,
    list_user_team_access,
    set_user_team_memberships,
)
from terrasatch.identity.models import MembershipRole
from terrasatch.identity.service import list_teams
from terrasatch.organizations.service import list_organizations, resolve_organization

router = APIRouter(tags=["admin-members"])


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


@router.get("/admin/members", response_class=HTMLResponse, include_in_schema=False)
async def admin_members(
    request: Request,
    organization: str = "",
) -> HTMLResponse:
    settings = request.app.state.settings
    _require_authenticated(request, settings)
    organizations = await _run_database(settings, list_organizations)
    selected = None
    if organization:
        selected = await _run_database(
            settings,
            lambda session: resolve_organization(session, organization),
        )
    elif organizations:
        selected = organizations[0]

    members = []
    teams = []
    member_team_names: dict[UUID, list[str]] = {}
    if selected is not None:
        members = await _run_database(
            settings,
            lambda session: list_organization_members(
                session,
                organization_id=selected.id,
            ),
        )
        teams = await _run_database(
            settings,
            lambda session: list_teams(
                session,
                organization_id=selected.id,
                enabled=True,
            ),
        )
        for _membership, user in members:
            team_access = await _run_database(
                settings,
                lambda session, user_id=user.id: list_user_team_access(
                    session,
                    user_id=user_id,
                    organization_id=selected.id,
                ),
            )
            member_team_names[user.id] = [item.team_name for item in team_access]

    options = "".join(
        f'<option value="{_attr(org.id)}"{" selected" if selected and org.id == selected.id else ""}>{escape(org.name)}</option>'
        for org in organizations
    )
    rows = "".join(
        f"<tr><td>{escape(user.display_name)}</td><td>{escape(user.email)}</td>"
        f"<td>{escape(membership.role.value.upper())}</td>"
        f"<td>{escape(', '.join(member_team_names.get(user.id, [])) or 'No teams')}</td>"
        f"<td>{'enabled' if membership.enabled and user.enabled else 'disabled'}</td></tr>"
        for membership, user in members
    ) or '<tr><td colspan="5" class="muted">No organization users yet.</td></tr>'
    team_options = "".join(
        f'<option value="{_attr(team.id)}">{escape(team.name)}</option>' for team in teams
    )
    org_id = str(selected.id) if selected else ""
    csrf = issue_csrf_token(request.session)
    return HTMLResponse(
        f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TerraSatch Members</title>{_styles()}</head><body><header><a href="/admin"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>MEMBERS & ACCESS</b></span></a><nav><a href="/admin">Operations</a><a href="/portal">Portal</a></nav></header><main><section class="head"><div><h1>Organization users</h1><p>Create individual browser accounts, assign one organization role, and explicitly choose the teams each employee may operate within.</p></div><form method="get"><label>Organization<select name="organization" onchange="this.form.submit()">{options}</select></label></form></section><section class="split"><div class="panel"><h2>Members</h2><div class="table"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Teams</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></div></div><div class="panel"><h2>Create or update member</h2><form class="member-form" method="post" action="/admin/members"><input type="hidden" name="csrf_token" value="{_attr(csrf)}"><input type="hidden" name="organization" value="{_attr(org_id)}"><label>Display name<input name="display_name" required></label><label>Email<input type="email" name="email" required></label><label>Role<select name="role"><option value="viewer">Viewer</option><option value="operator">Operator</option><option value="admin">Admin</option><option value="owner">Owner</option></select></label><label>Teams<select name="team_ids" multiple size="5">{team_options}</select></label><label>Temporary / reset password<input type="password" name="password" minlength="12" required autocomplete="new-password"></label><button type="submit" {'disabled' if not selected else ''}>Save member</button><small>One email can belong to multiple organizations. Team access is explicit inside each organization. Passwords are stored only as scrypt hashes.</small></form></div></section><section class="roles"><div><strong>OWNER</strong><span>Organization authority.</span></div><div><strong>ADMIN</strong><span>Administrative member.</span></div><div><strong>OPERATOR</strong><span>Operational user.</span></div><div><strong>VIEWER</strong><span>Read-oriented access.</span></div></section></main></body></html>'''
    )


@router.post("/admin/members", include_in_schema=False)
async def admin_member_upsert(
    request: Request,
    organization: Annotated[str, Form()],
    email: Annotated[str, Form()],
    display_name: Annotated[str, Form()],
    role: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    team_ids: Annotated[list[str] | None, Form()] = None,
) -> RedirectResponse:
    settings = request.app.state.settings
    _require_authenticated(request, settings)
    _verify_csrf(request, csrf_token)
    try:
        organization_id = UUID(organization)
        member_role = MembershipRole(role.lower())
        parsed_team_ids = {UUID(value) for value in team_ids or []}
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization, team, or role",
        ) from error

    async def operation(session):
        user, membership = await create_or_update_organization_member(
            session,
            organization_id=organization_id,
            email=email,
            display_name=display_name,
            password=password,
            role=member_role,
            settings=settings,
        )
        await set_user_team_memberships(
            session,
            organization_id=organization_id,
            user_id=user.id,
            team_ids=parsed_team_ids,
        )
        return user, membership

    await _run_database(settings, operation)
    return RedirectResponse(
        f"/admin/members?organization={organization_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _styles() -> str:
    return '''<style>:root{color-scheme:dark;--bg:#080b0d;--p:#101519;--line:rgba(255,255,255,.1);--t:#edf1f0;--m:#8f989e;--o:#f47a20;--g:#6ee7a0;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:13px/1.5 Inter,system-ui,sans-serif}header{height:68px;border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 28px}header>a{display:flex;align-items:center;gap:10px;text-decoration:none;color:inherit}header img{width:42px;height:42px}header strong,header b{display:block}header b{color:var(--o);font:9px var(--mono);letter-spacing:.1em}nav{margin-left:auto;display:flex;gap:18px}nav a{color:var(--m);text-decoration:none}main{max-width:1400px;margin:auto;padding:28px}.head{display:flex;justify-content:space-between;gap:24px;align-items:end}.head h1{font-size:30px;margin:0}.head p{color:var(--m);max-width:760px}.head label,.member-form label{display:grid;gap:5px;color:var(--m);font-size:10px}.split{display:grid;grid-template-columns:1.3fr .7fr;gap:14px;margin-top:18px}.panel{border:1px solid var(--line);border-radius:10px;background:var(--p);overflow:hidden}.panel h2{font-size:13px;margin:0;padding:14px 16px;border-bottom:1px solid var(--line)}.table{overflow:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--line)}th{color:var(--m);font:8px var(--mono)}.muted{color:var(--m);text-align:center}.member-form{display:grid;gap:11px;padding:16px}.member-form input,.member-form select,.head select{background:#0b1013;border:1px solid var(--line);color:var(--t);padding:9px;border-radius:6px}.member-form button{padding:10px;border-radius:6px;border:1px solid rgba(244,122,32,.45);background:rgba(244,122,32,.11);color:#ffad59;cursor:pointer}.member-form small{color:var(--m)}code{font-family:var(--mono)}.roles{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px}.roles div{border:1px solid var(--line);padding:11px;border-radius:8px}.roles strong{display:block;color:var(--o);font:9px var(--mono)}.roles span{color:var(--m);font-size:10px}@media(max-width:800px){header,main{padding-left:14px;padding-right:14px}.split{grid-template-columns:1fr}.head{align-items:stretch;flex-direction:column}.roles{grid-template-columns:repeat(2,1fr)}}</style>'''
