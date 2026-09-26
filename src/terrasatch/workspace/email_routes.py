"""Signed Resend inbound webhook and authenticated workspace email API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from terrasatch.billing.resend_webhook import verify_resend_webhook
from terrasatch.database.session import create_session_factory
from terrasatch.errors import InvalidConfiguration
from terrasatch.workspace.email_service import (
    get_workspace_email,
    ingest_resend_received_email,
    is_internal_workspace_user,
    list_workspace_emails,
    mark_workspace_email_read,
    reply_to_workspace_email,
    send_workspace_email,
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


@router.post("/email/resend/webhook")
async def resend_inbound_email_webhook(request: Request) -> dict[str, object]:
    """Persist complete inbound messages only after verifying Resend's Svix signature."""

    settings = request.app.state.settings
    if settings.resend_webhook_secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    raw_payload = await request.body()
    if len(raw_payload) > 64_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Webhook payload is too large",
        )
    try:
        event, webhook_id = verify_resend_webhook(
            raw_payload=raw_payload,
            headers=request.headers,
            secret=settings.resend_webhook_secret,
        )
    except InvalidConfiguration as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Resend webhook",
        ) from error

    async with create_session_factory(settings)() as session:
        try:
            result = await ingest_resend_received_email(
                session,
                settings,
                event=event,
                webhook_id=webhook_id,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return {
        "matched": result.matched,
        "duplicate": result.duplicate,
        "event_type": result.event_type,
        "email_id": str(result.email_id) if result.email_id else None,
    }


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
