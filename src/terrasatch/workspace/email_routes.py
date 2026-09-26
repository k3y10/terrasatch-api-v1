"""Signed Resend inbound webhook and authenticated workspace email API."""
# ruff: noqa: E501

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from terrasatch.database.session import create_session_factory
from terrasatch.identity.models import Membership, User
from terrasatch.workspace.email_service import (
    get_workspace_attachment,
    get_workspace_email,
    is_internal_workspace_user,
    list_workspace_emails,
    list_mailbox_delegates,
    mark_workspace_email_read,
    normalize_email_address,
    remove_mailbox_delegate,
    reply_to_workspace_email,
    send_workspace_email,
    set_mailbox_delegate,
)
from terrasatch.workspace.routes import access, csrf

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace-email"])


class ComposeEmail(BaseModel):
    request_id: UUID
    sender: str = Field(min_length=3, max_length=320)
    recipients: list[str] = Field(min_length=1, max_length=10)
    subject: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=20_000)


class ReplyEmail(BaseModel):
    request_id: UUID
    text: str = Field(min_length=1, max_length=20_000)


class MailboxDelegationRequest(BaseModel):
    mailbox: str = Field(min_length=3, max_length=320)
    delegate_email: str = Field(min_length=5, max_length=320)
    can_send: bool = False


class MailboxDelegationRevoke(BaseModel):
    mailbox: str = Field(min_length=3, max_length=320)
    delegate_email: str = Field(min_length=5, max_length=320)


async def _organization_delegate_user(
    session,
    *,
    organization_id: UUID,
    email: str,
) -> User:
    normalized = normalize_email_address(email)
    user = await session.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == organization_id,
            Membership.enabled.is_(True),
            User.enabled.is_(True),
            func.lower(User.email) == normalized,
        )
    )
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Delegate must be an enabled member of this organization",
        )
    return user


@router.get("/organizations/{organization_id}/email-access/delegations")
async def workspace_email_delegations(
    organization_id: UUID,
    mailbox: str,
    request: Request,
) -> dict[str, object]:
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        if not is_internal_workspace_user(user):
            raise HTTPException(status_code=403, detail="TerraSatch email access required")
        rows = await list_mailbox_delegates(
            session,
            actor=user,
            role=membership.role,
            mailbox=mailbox,
        )
        delegate_ids = [row.user_id for row in rows]
        delegates = {}
        if delegate_ids:
            delegates = {
                item.id: item.email
                for item in await session.scalars(
                    select(User).where(User.id.in_(delegate_ids))
                )
            }
        return {
            "mailbox": normalize_email_address(mailbox),
            "delegates": [
                {
                    "user_id": str(row.user_id),
                    "email": delegates.get(row.user_id, ""),
                    "can_send": bool(row.can_send),
                }
                for row in rows
            ],
        }


@router.post("/organizations/{organization_id}/email-access/delegations")
async def workspace_email_delegate(
    organization_id: UUID,
    payload: MailboxDelegationRequest,
    request: Request,
) -> dict[str, object]:
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        actor, membership = await access(request, session, organization_id)
        if not is_internal_workspace_user(actor):
            raise HTTPException(status_code=403, detail="TerraSatch email access required")
        delegate = await _organization_delegate_user(
            session,
            organization_id=organization_id,
            email=payload.delegate_email,
        )
        row = await set_mailbox_delegate(
            session,
            actor=actor,
            role=membership.role,
            mailbox=payload.mailbox,
            delegate=delegate,
            can_send=payload.can_send,
        )
        await session.commit()
        return {
            "mailbox": row.mailbox_address,
            "delegate_email": delegate.email,
            "can_send": bool(row.can_send),
        }


@router.post("/organizations/{organization_id}/email-access/delegations/revoke")
async def workspace_email_delegate_revoke(
    organization_id: UUID,
    payload: MailboxDelegationRevoke,
    request: Request,
) -> dict[str, bool]:
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        actor, membership = await access(request, session, organization_id)
        if not is_internal_workspace_user(actor):
            raise HTTPException(status_code=403, detail="TerraSatch email access required")
        delegate = await _organization_delegate_user(
            session,
            organization_id=organization_id,
            email=payload.delegate_email,
        )
        removed = await remove_mailbox_delegate(
            session,
            actor=actor,
            role=membership.role,
            mailbox=payload.mailbox,
            delegate=delegate,
        )
        await session.commit()
        return {"removed": removed}


@router.get("/organizations/{organization_id}/email")
async def workspace_email_list(
    organization_id: UUID,
    request: Request,
    response: Response,
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        if not is_internal_workspace_user(user):
            raise HTTPException(status_code=403, detail="TerraSatch email access required")
        messages = await list_workspace_emails(
            session,
            user=user,
            role=membership.role,
        )
        return jsonable_encoder({"messages": messages})


@router.get("/organizations/{organization_id}/email/{email_id}")
async def workspace_email_detail(
    organization_id: UUID,
    email_id: UUID,
    request: Request,
    response: Response,
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        if not is_internal_workspace_user(user):
            raise HTTPException(status_code=403, detail="TerraSatch email access required")
        message = await get_workspace_email(
            session,
            user=user,
            role=membership.role,
            email_id=email_id,
        )
        return jsonable_encoder(
            {
                "id": str(message.id),
                "direction": message.direction,
                "mailbox": message.received_for,
                "from": message.from_address,
                "to": list(message.to_addresses or []),
                "cc": list(message.cc_addresses or []),
                "bcc": list(message.bcc_addresses or []),
                "reply_to": list(message.reply_to or []),
                "subject": message.subject,
                "text": message.text_body,
                "html": message.html_body,
                "headers": dict(message.headers or {}),
                "attachments": list(message.attachments or []),
                "message_id": message.internet_message_id,
                "received_at": message.received_at,
            }
        )


@router.get("/organizations/{organization_id}/email/{email_id}/attachments/{attachment_id}")
async def workspace_email_attachment(
    organization_id: UUID,
    email_id: UUID,
    attachment_id: str,
    request: Request,
    response: Response,
) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        if not is_internal_workspace_user(user):
            raise HTTPException(status_code=403, detail="TerraSatch email access required")
        return await get_workspace_attachment(
            session,
            request.app.state.settings,
            user=user,
            role=membership.role,
            email_id=email_id,
            attachment_id=attachment_id,
        )


@router.post("/organizations/{organization_id}/email/{email_id}/read")
async def workspace_email_read(
    organization_id: UUID,
    email_id: UUID,
    request: Request,
) -> dict[str, bool]:
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        await get_workspace_email(
            session,
            user=user,
            role=membership.role,
            email_id=email_id,
        )
        await mark_workspace_email_read(session, user=user, email_id=email_id)
        await session.commit()
    return {"read": True}


@router.post("/organizations/{organization_id}/email")
async def workspace_email_compose(
    organization_id: UUID,
    payload: ComposeEmail,
    request: Request,
) -> dict[str, str]:
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        if not is_internal_workspace_user(user):
            raise HTTPException(status_code=403, detail="TerraSatch email access required")
        row = await send_workspace_email(
            session,
            request.app.state.settings,
            user=user,
            role=membership.role,
            sender=payload.sender,
            recipients=payload.recipients,
            subject=payload.subject,
            text=payload.text,
            request_id=payload.request_id,
        )
        await session.commit()
        return {"id": str(row.id), "provider_email_id": row.provider_email_id}


@router.post("/organizations/{organization_id}/email/{email_id}/reply")
async def workspace_email_reply(
    organization_id: UUID,
    email_id: UUID,
    payload: ReplyEmail,
    request: Request,
) -> dict[str, str]:
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        if not is_internal_workspace_user(user):
            raise HTTPException(status_code=403, detail="TerraSatch email access required")
        row = await reply_to_workspace_email(
            session,
            request.app.state.settings,
            user=user,
            role=membership.role,
            email_id=email_id,
            text=payload.text,
            request_id=payload.request_id,
        )
        await session.commit()
        return {"id": str(row.id), "provider_email_id": row.provider_email_id}
