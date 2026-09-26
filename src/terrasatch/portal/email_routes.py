"""Human-facing TerraSatch workspace email pages."""
# ruff: noqa: E501

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from terrasatch.admin.security import issue_csrf_token
from terrasatch.database.session import create_session_factory
from terrasatch.identity.access import get_user_organization_access, list_user_access
from terrasatch.identity.models import Membership, User
from terrasatch.portal.email_ui import render_email_detail, render_email_inbox
from terrasatch.portal.routes import _enabled, _require_user, _verify_csrf
from terrasatch.workspace.email_service import (
    get_workspace_attachment,
    get_workspace_email,
    is_internal_workspace_user,
    list_mailbox_delegates,
    list_workspace_emails,
    manageable_mailboxes,
    mark_workspace_email_read,
    remove_mailbox_delegate,
    reply_to_workspace_email,
    send_workspace_email,
    sendable_mailboxes,
    set_mailbox_delegate,
)

router = APIRouter(tags=["portal-email"])


async def _email_context(request: Request, organization: str):
    settings = request.app.state.settings
    _enabled(settings)
    user_id = await _require_user(request, settings)
    factory = create_session_factory(settings)
    async with factory() as session:
        user = await session.get(User, user_id)
        if user is None or not user.enabled:
            raise HTTPException(status_code=401, detail="Sign in required")
        if not is_internal_workspace_user(user):
            raise HTTPException(status_code=403, detail="TerraSatch email access required")
        access = await list_user_access(session, user_id=user.id)
        if not access:
            raise HTTPException(status_code=403, detail="No organization access")
        remembered = str(request.session.get("portal_organization") or "")
        selector = organization or remembered
        selected_access = next(
            (item for item in access if str(item.organization_id) == selector),
            access[0],
        )
        membership = await get_user_organization_access(
            session,
            user_id=user.id,
            organization_id=selected_access.organization_id,
        )
        request.session["portal_organization"] = str(membership.organization_id)
        return user, membership


@router.get("/portal/email", include_in_schema=False, response_model=None)
async def portal_email_inbox(
    request: Request,
    organization: str = "",
) -> HTMLResponse | RedirectResponse:
    try:
        user, membership = await _email_context(request, organization)
    except HTTPException as error:
        if error.status_code == 401:
            return RedirectResponse("/portal/login", status_code=status.HTTP_303_SEE_OTHER)
        raise

    factory = create_session_factory(request.app.state.settings)
    async with factory() as session:
        messages = await list_workspace_emails(
            session,
            user=user,
            role=membership.role,
        )
        senders = await sendable_mailboxes(
            session,
            user=user,
            role=membership.role,
        )
        managed_mailboxes = manageable_mailboxes(user, membership.role)
        member_rows = list(
            await session.scalars(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.organization_id == membership.organization_id,
                    Membership.enabled.is_(True),
                    User.enabled.is_(True),
                    User.email.ilike("%@terrasatch.com"),
                )
                .order_by(User.display_name, User.email)
            )
        )
        delegates: dict[str, list[dict[str, object]]] = {}
        for mailbox in managed_mailboxes:
            rows = await list_mailbox_delegates(
                session,
                actor=user,
                role=membership.role,
                mailbox=mailbox,
            )
            delegate_users = {item.id: item for item in member_rows}
            delegates[mailbox] = [
                {
                    "email": delegate_users[row.user_id].email
                    if row.user_id in delegate_users
                    else str(row.user_id),
                    "can_send": bool(row.can_send),
                }
                for row in rows
            ]
    return HTMLResponse(
        render_email_inbox(
            organization_id=str(membership.organization_id),
            organization_name=membership.organization_name,
            messages=messages,
            senders=senders,
            manageable_mailboxes=managed_mailboxes,
            organization_members=[
                {"email": item.email, "display_name": item.display_name}
                for item in member_rows
            ],
            delegates=delegates,
            csrf_token=issue_csrf_token(request.session),
        ),
        headers={"Cache-Control": "no-store"},
    )





@router.post("/portal/email/access/delegate", include_in_schema=False, response_model=None)
async def portal_email_delegate(
    request: Request,
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    mailbox: Annotated[str, Form()],
    delegate_email: Annotated[str, Form()],
    can_send: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    _verify_csrf(request, csrf_token)
    actor, membership = await _email_context(request, organization)
    factory = create_session_factory(request.app.state.settings)
    async with factory() as session:
        delegate = await session.scalar(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == membership.organization_id,
                Membership.enabled.is_(True),
                User.enabled.is_(True),
                User.email == delegate_email.strip().casefold(),
            )
        )
        if delegate is None:
            raise HTTPException(status_code=404, detail="Internal delegate was not found")
        await set_mailbox_delegate(
            session,
            actor=actor,
            role=membership.role,
            mailbox=mailbox,
            delegate=delegate,
            can_send=can_send == "on",
        )
        await session.commit()
    return RedirectResponse(
        f"/portal/email?organization={membership.organization_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/portal/email/access/revoke", include_in_schema=False, response_model=None)
async def portal_email_delegate_revoke(
    request: Request,
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    mailbox: Annotated[str, Form()],
    delegate_email: Annotated[str, Form()],
) -> RedirectResponse:
    _verify_csrf(request, csrf_token)
    actor, membership = await _email_context(request, organization)
    factory = create_session_factory(request.app.state.settings)
    async with factory() as session:
        delegate = await session.scalar(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == membership.organization_id,
                Membership.enabled.is_(True),
                User.enabled.is_(True),
                User.email == delegate_email.strip().casefold(),
            )
        )
        if delegate is None:
            raise HTTPException(status_code=404, detail="Internal delegate was not found")
        await remove_mailbox_delegate(
            session,
            actor=actor,
            role=membership.role,
            mailbox=mailbox,
            delegate=delegate,
        )
        await session.commit()
    return RedirectResponse(
        f"/portal/email?organization={membership.organization_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/portal/email/{email_id}", include_in_schema=False, response_model=None)
async def portal_email_detail(
    email_id: UUID,
    request: Request,
    organization: str = "",
) -> HTMLResponse | RedirectResponse:
    try:
        user, membership = await _email_context(request, organization)
    except HTTPException as error:
        if error.status_code == 401:
            return RedirectResponse("/portal/login", status_code=status.HTTP_303_SEE_OTHER)
        raise

    factory = create_session_factory(request.app.state.settings)
    async with factory() as session:
        message = await get_workspace_email(
            session,
            user=user,
            role=membership.role,
            email_id=email_id,
        )
        await mark_workspace_email_read(session, user=user, email_id=email_id)
        await session.commit()
        reply_allowed = message.received_for in await sendable_mailboxes(
            session,
            user=user,
            role=membership.role,
        )
    return HTMLResponse(
        render_email_detail(
            organization_id=str(membership.organization_id),
            organization_name=membership.organization_name,
            message=message,
            reply_allowed=reply_allowed,
            csrf_token=issue_csrf_token(request.session),
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/portal/email/{email_id}/attachments/{attachment_id}",
    include_in_schema=False,
    response_model=None,
)
async def portal_email_attachment(
    email_id: UUID,
    attachment_id: str,
    request: Request,
    organization: str = "",
) -> RedirectResponse:
    user, membership = await _email_context(request, organization)
    factory = create_session_factory(request.app.state.settings)
    async with factory() as session:
        attachment = await get_workspace_attachment(
            session,
            request.app.state.settings,
            user=user,
            role=membership.role,
            email_id=email_id,
            attachment_id=attachment_id,
        )
    return RedirectResponse(
        attachment["download_url"],
        status_code=status.HTTP_302_FOUND,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/portal/email/compose", include_in_schema=False, response_model=None)
async def portal_email_compose(
    request: Request,
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    sender: Annotated[str, Form()],
    recipient: Annotated[str, Form()],
    subject: Annotated[str, Form()],
    body: Annotated[str, Form()],
) -> RedirectResponse:
    _verify_csrf(request, csrf_token)
    user, membership = await _email_context(request, organization)
    factory = create_session_factory(request.app.state.settings)
    async with factory() as session:
        await send_workspace_email(
            session,
            request.app.state.settings,
            user=user,
            role=membership.role,
            sender=sender,
            recipients=[recipient],
            subject=subject,
            text=body,
            request_id=uuid4(),
        )
        await session.commit()
    return RedirectResponse(
        f"/portal/email?organization={membership.organization_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/portal/email/{email_id}/reply",
    include_in_schema=False,
    response_model=None,
)
async def portal_email_reply(
    email_id: UUID,
    request: Request,
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    body: Annotated[str, Form()],
) -> RedirectResponse:
    _verify_csrf(request, csrf_token)
    user, membership = await _email_context(request, organization)
    factory = create_session_factory(request.app.state.settings)
    async with factory() as session:
        await reply_to_workspace_email(
            session,
            request.app.state.settings,
            user=user,
            role=membership.role,
            email_id=email_id,
            text=body,
            request_id=uuid4(),
        )
        await session.commit()
    return RedirectResponse(
        f"/portal/email/{email_id}?organization={membership.organization_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
