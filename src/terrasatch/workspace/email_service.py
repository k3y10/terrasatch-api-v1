"""Resend-backed email receiving, workspace visibility, and human replies."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable, ResourceNotFound
from terrasatch.identity.models import MembershipRole, User
from terrasatch.workspace.email_models import (
    WorkspaceEmailDelegate,
    WorkspaceEmailMessage,
    WorkspaceEmailRead,
)

TERRASATCH_EMAIL_DOMAIN = "terrasatch.com"
OPS_MAILBOX = f"ops@{TERRASATCH_EMAIL_DOMAIN}"
SUPPORT_MAILBOX = f"support@{TERRASATCH_EMAIL_DOMAIN}"
LEGAL_MAILBOX = f"legal@{TERRASATCH_EMAIL_DOMAIN}"
BILLING_MAILBOX = f"billing@{TERRASATCH_EMAIL_DOMAIN}"
_SHARED_MAILBOXES = {OPS_MAILBOX, SUPPORT_MAILBOX, LEGAL_MAILBOX, BILLING_MAILBOX}
_MAX_TEXT_BODY = 2_000_000
_MAX_HTML_BODY = 4_000_000


@dataclass(frozen=True, slots=True)
class InboundEmailResult:
    matched: bool
    duplicate: bool
    event_type: str
    email_id: UUID | None = None


def normalize_email_address(value: str) -> str:
    """Extract and normalize the mailbox address from an RFC-style address."""

    _display, address = parseaddr(str(value or ""))
    normalized = address.strip().casefold()
    return normalized if "@" in normalized else ""


def is_terrasatch_address(value: str) -> bool:
    return normalize_email_address(value).endswith(f"@{TERRASATCH_EMAIL_DOMAIN}")


def is_internal_workspace_user(user: User) -> bool:
    return is_terrasatch_address(user.email)


def _base_mailbox_permissions(
    user: User,
    role: MembershipRole,
) -> dict[str, bool]:
    """Return policy-granted mailbox visibility mapped to send permission."""

    own = normalize_email_address(user.email)
    if not own.endswith(f"@{TERRASATCH_EMAIL_DOMAIN}"):
        return {}

    permissions: dict[str, bool] = {
        own: role != MembershipRole.VIEWER,
    }
    if role in {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.OPERATOR}:
        permissions[SUPPORT_MAILBOX] = True
    if role in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        permissions[OPS_MAILBOX] = True
        permissions[BILLING_MAILBOX] = False
    if role == MembershipRole.OWNER:
        permissions[LEGAL_MAILBOX] = True
    return permissions


async def mailbox_permissions(
    session: AsyncSession,
    *,
    user: User,
    role: MembershipRole,
) -> dict[str, bool]:
    """Resolve policy plus explicit per-user delegation for internal mailboxes."""

    permissions = _base_mailbox_permissions(user, role)
    if not is_internal_workspace_user(user):
        return permissions

    delegated = list(
        await session.scalars(
            select(WorkspaceEmailDelegate).where(
                WorkspaceEmailDelegate.user_id == user.id
            )
        )
    )
    for item in delegated:
        mailbox = normalize_email_address(item.mailbox_address)
        if not mailbox.endswith(f"@{TERRASATCH_EMAIL_DOMAIN}"):
            continue
        can_send = bool(item.can_send)
        if mailbox == BILLING_MAILBOX:
            can_send = False
        permissions[mailbox] = permissions.get(mailbox, False) or can_send
        if mailbox not in permissions:
            permissions[mailbox] = can_send
    return permissions


async def sendable_mailboxes(
    session: AsyncSession,
    *,
    user: User,
    role: MembershipRole,
) -> list[str]:
    """Return mailboxes this human may explicitly send as."""

    permissions = await mailbox_permissions(session, user=user, role=role)
    return sorted(mailbox for mailbox, can_send in permissions.items() if can_send)


async def visible_mailboxes(
    session: AsyncSession,
    *,
    user: User,
    role: MembershipRole,
) -> list[str]:
    """Return every mailbox this human may read."""

    permissions = await mailbox_permissions(session, user=user, role=role)
    return sorted(permissions)


def mailbox_label(address: str) -> str:
    normalized = normalize_email_address(address)
    labels = {
        BILLING_MAILBOX: "Billing",
        SUPPORT_MAILBOX: "Support",
        OPS_MAILBOX: "Operations",
        LEGAL_MAILBOX: "Legal",
    }
    return labels.get(normalized, normalized.split("@", 1)[0].replace(".", " ").title())


def _can_manage_mailbox(
    actor: User,
    role: MembershipRole,
    mailbox: str,
) -> bool:
    own = normalize_email_address(actor.email)
    if mailbox == own:
        return True
    return mailbox in _SHARED_MAILBOXES and role == MembershipRole.OWNER


async def set_mailbox_delegate(
    session: AsyncSession,
    *,
    actor: User,
    role: MembershipRole,
    mailbox: str,
    delegate: User,
    can_send: bool,
) -> WorkspaceEmailDelegate:
    """Create or update explicit mailbox access without broadening organization roles."""

    normalized = normalize_email_address(mailbox)
    if not normalized.endswith(f"@{TERRASATCH_EMAIL_DOMAIN}"):
        raise InvalidConfiguration("Delegated mailbox must use the TerraSatch email domain")
    if not _can_manage_mailbox(actor, role, normalized):
        raise InvalidConfiguration("You are not allowed to manage this mailbox")
    if not is_internal_workspace_user(delegate):
        raise InvalidConfiguration("Mailbox delegates must use an internal TerraSatch account")
    if normalized == BILLING_MAILBOX:
        can_send = False

    existing = await session.scalar(
        select(WorkspaceEmailDelegate).where(
            WorkspaceEmailDelegate.mailbox_address == normalized,
            WorkspaceEmailDelegate.user_id == delegate.id,
        )
    )
    if existing is None:
        existing = WorkspaceEmailDelegate(
            mailbox_address=normalized,
            user_id=delegate.id,
            can_send=can_send,
            created_by_user_id=actor.id,
        )
        session.add(existing)
    else:
        existing.can_send = can_send
        existing.created_by_user_id = actor.id
    await session.flush()
    return existing


async def remove_mailbox_delegate(
    session: AsyncSession,
    *,
    actor: User,
    role: MembershipRole,
    mailbox: str,
    delegate: User,
) -> bool:
    """Remove one explicit mailbox delegation."""

    normalized = normalize_email_address(mailbox)
    if not _can_manage_mailbox(actor, role, normalized):
        raise InvalidConfiguration("You are not allowed to manage this mailbox")
    existing = await session.scalar(
        select(WorkspaceEmailDelegate).where(
            WorkspaceEmailDelegate.mailbox_address == normalized,
            WorkspaceEmailDelegate.user_id == delegate.id,
        )
    )
    if existing is None:
        return False
    await session.delete(existing)
    await session.flush()
    return True


async def list_mailbox_delegates(
    session: AsyncSession,
    *,
    actor: User,
    role: MembershipRole,
    mailbox: str,
) -> list[WorkspaceEmailDelegate]:
    """List explicit delegates only when the actor can manage the mailbox."""

    normalized = normalize_email_address(mailbox)
    if not _can_manage_mailbox(actor, role, normalized):
        raise InvalidConfiguration("You are not allowed to manage this mailbox")
    return list(
        await session.scalars(
            select(WorkspaceEmailDelegate)
            .where(WorkspaceEmailDelegate.mailbox_address == normalized)
            .order_by(WorkspaceEmailDelegate.created_at)
        )
    )


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _headers(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[key[:255]] = item
        elif isinstance(item, list):
            result[key[:255]] = [str(entry)[:4000] for entry in item[:50]]
    return result


def _attachments(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    allowed = {
        "id",
        "filename",
        "content_type",
        "content_disposition",
        "content_id",
        "size",
    }
    result: list[dict[str, object]] = []
    for item in value[:100]:
        if not isinstance(item, dict):
            continue
        clean = {
            str(key): raw
            for key, raw in item.items()
            if key in allowed and isinstance(raw, (str, int, float, bool))
        }
        result.append(clean)
    return result


def _parse_time(value: object) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _received_for(payload: dict[str, object], event_data: dict[str, object]) -> str:
    candidates: list[str] = []
    candidates.extend(_string_list(payload.get("received_for")))
    candidates.extend(_string_list(payload.get("to")))
    candidates.extend(_string_list(event_data.get("to")))
    for candidate in candidates:
        normalized = normalize_email_address(candidate)
        if normalized.endswith(f"@{TERRASATCH_EMAIL_DOMAIN}"):
            return normalized
    return ""


async def _recipient_user(
    session: AsyncSession,
    received_for: str,
) -> User | None:
    return await session.scalar(
        select(User).where(
            func.lower(User.email) == received_for,
            User.enabled.is_(True),
        )
    )


async def ingest_resend_received_email(
    session: AsyncSession,
    settings: Settings,
    *,
    event: dict[str, object],
    webhook_id: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> InboundEmailResult:
    """Fetch and persist the complete Resend message for one signed email.received event."""

    event_type = str(event.get("type") or "")
    if event_type != "email.received":
        return InboundEmailResult(False, False, event_type)

    event_data = event.get("data")
    if not isinstance(event_data, dict):
        raise InvalidConfiguration("Resend received-email event is missing its data object")
    provider_email_id = str(event_data.get("email_id") or "").strip()
    if not provider_email_id:
        raise InvalidConfiguration("Resend received-email event is missing data.email_id")

    existing = await session.scalar(
        select(WorkspaceEmailMessage).where(
            WorkspaceEmailMessage.provider_email_id == provider_email_id
        )
    )
    if existing is not None:
        return InboundEmailResult(True, True, event_type, existing.id)

    if settings.resend_api_key is None:
        raise ProviderUnavailable("Resend API key is unavailable for inbound email retrieval")

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
            response = await client.get(
                f"https://api.resend.com/emails/receiving/{provider_email_id}",
                headers=headers,
            )
        response.raise_for_status()
        raw = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderUnavailable("Resend inbound email retrieval failed") from error

    payload = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
    if not isinstance(payload, dict):
        raise ProviderUnavailable("Resend inbound email response is invalid")

    received_for = _received_for(payload, event_data)
    if not received_for:
        return InboundEmailResult(False, False, event_type)

    recipient = await _recipient_user(session, received_for)
    subject = str(payload.get("subject") or event_data.get("subject") or "")[:10_000]
    text_body = payload.get("text")
    html_body = payload.get("html")
    message = WorkspaceEmailMessage(
        provider_email_id=provider_email_id[:255],
        provider_event_id=webhook_id[:255] or None,
        direction="inbound",
        recipient_user_id=recipient.id if recipient is not None else None,
        internet_message_id=(
            str(payload.get("message_id") or event_data.get("message_id") or "")[:1024] or None
        ),
        received_for=received_for,
        from_address=str(payload.get("from") or event_data.get("from") or "")[:1000],
        to_addresses=_string_list(payload.get("to") or event_data.get("to")),
        cc_addresses=_string_list(payload.get("cc") or event_data.get("cc")),
        bcc_addresses=_string_list(payload.get("bcc") or event_data.get("bcc")),
        reply_to=_string_list(payload.get("reply_to")),
        subject=subject,
        text_body=(
            str(text_body)[:_MAX_TEXT_BODY] if isinstance(text_body, str) else None
        ),
        html_body=(
            str(html_body)[:_MAX_HTML_BODY] if isinstance(html_body, str) else None
        ),
        headers=_headers(payload.get("headers")),
        attachments=_attachments(payload.get("attachments") or event_data.get("attachments")),
        received_at=_parse_time(payload.get("created_at") or event.get("created_at")),
    )
    session.add(message)
    await session.flush()
    return InboundEmailResult(True, False, event_type, message.id)


async def _visible_statement(
    session: AsyncSession,
    *,
    user: User,
    role: MembershipRole,
):
    statement = select(WorkspaceEmailMessage)
    mailboxes = await visible_mailboxes(session, user=user, role=role)
    if not mailboxes:
        return statement.where(False)
    return statement.where(
        func.lower(WorkspaceEmailMessage.received_for).in_(mailboxes)
    )


async def list_workspace_emails(
    session: AsyncSession,
    *,
    user: User,
    role: MembershipRole,
    limit: int = 100,
) -> list[dict[str, object]]:
    rows = list(
        await session.scalars(
            (await _visible_statement(session, user=user, role=role))
            .order_by(WorkspaceEmailMessage.received_at.desc())
            .limit(max(1, min(limit, 200)))
        )
    )
    if not rows:
        return []
    read_ids = set(
        await session.scalars(
            select(WorkspaceEmailRead.email_id).where(
                WorkspaceEmailRead.user_id == user.id,
                WorkspaceEmailRead.email_id.in_([row.id for row in rows]),
            )
        )
    )
    payloads: list[dict[str, object]] = []
    for row in rows:
        body = row.text_body or ""
        preview = " ".join(body.split())[:220]
        payloads.append(
            {
                "id": str(row.id),
                "direction": row.direction,
                "mailbox": row.received_for,
                "from": row.from_address,
                "to": list(row.to_addresses or []),
                "subject": row.subject,
                "preview": preview,
                "received_at": row.received_at,
                "attachment_count": len(row.attachments or []),
                "read": row.id in read_ids,
                "reply_allowed": row.received_for
                in await sendable_mailboxes(session, user=user, role=role),
            }
        )
    return payloads


async def get_workspace_email(
    session: AsyncSession,
    *,
    user: User,
    role: MembershipRole,
    email_id: UUID,
) -> WorkspaceEmailMessage:
    message = await session.scalar(
        (await _visible_statement(session, user=user, role=role)).where(
            WorkspaceEmailMessage.id == email_id
        )
    )
    if message is None:
        raise ResourceNotFound("Email was not found")
    return message


async def mark_workspace_email_read(
    session: AsyncSession,
    *,
    user: User,
    email_id: UUID,
) -> None:
    existing = await session.get(WorkspaceEmailRead, (email_id, user.id))
    if existing is None:
        session.add(
            WorkspaceEmailRead(
                email_id=email_id,
                user_id=user.id,
                read_at=datetime.now(UTC),
            )
        )
        await session.flush()


async def get_workspace_attachment(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    role: MembershipRole,
    email_id: UUID,
    attachment_id: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, str]:
    """Return a fresh provider-signed download URL after workspace authorization."""

    message = await get_workspace_email(
        session,
        user=user,
        role=role,
        email_id=email_id,
    )
    clean_attachment_id = attachment_id.strip()
    stored_attachment = next(
        (
            item
            for item in (message.attachments or [])
            if isinstance(item, dict)
            and str(item.get("id") or "") == clean_attachment_id
        ),
        None,
    )
    if stored_attachment is None:
        raise ResourceNotFound("Email attachment was not found")
    if message.direction != "inbound":
        raise ResourceNotFound("Email attachment was not found")
    if settings.resend_api_key is None:
        raise ProviderUnavailable("Resend API key is unavailable")

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
            response = await client.get(
                (
                    "https://api.resend.com/emails/receiving/"
                    f"{message.provider_email_id}/attachments/{clean_attachment_id}"
                ),
                headers=headers,
            )
        response.raise_for_status()
        raw = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderUnavailable("Resend attachment retrieval failed") from error

    payload = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
    if not isinstance(payload, dict):
        raise ProviderUnavailable("Resend attachment response is invalid")
    if str(payload.get("id") or "") != clean_attachment_id:
        raise ProviderUnavailable("Resend attachment response did not match the requested file")
    download_url = str(payload.get("download_url") or "").strip()
    if not download_url.startswith("https://"):
        raise ProviderUnavailable("Resend attachment download URL is invalid")
    return {
        "id": clean_attachment_id,
        "filename": str(
            payload.get("filename")
            or stored_attachment.get("filename")
            or "attachment"
        ),
        "content_type": str(
            payload.get("content_type")
            or stored_attachment.get("content_type")
            or "application/octet-stream"
        ),
        "download_url": download_url,
        "expires_at": str(payload.get("expires_at") or ""),
    }


async def _post_resend_email(
    settings: Settings,
    *,
    sender: str,
    recipients: list[str],
    subject: str,
    text: str,
    request_id: UUID,
    thread_message_id: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, str | None]:
    if settings.resend_api_key is None:
        raise ProviderUnavailable("Resend API key is unavailable")
    clean_subject = subject.strip()
    clean_text = text.strip()
    if not clean_subject or len(clean_subject) > 500:
        raise InvalidConfiguration("Email subject is required and must be 500 characters or less")
    if not clean_text or len(clean_text) > 20_000:
        raise InvalidConfiguration("Email body is required and must be 20000 characters or less")
    if not recipients or len(recipients) > 10:
        raise InvalidConfiguration("Email requires between 1 and 10 recipients")
    payload: dict[str, object] = {
        "from": sender,
        "to": recipients,
        "subject": clean_subject,
        "text": clean_text,
    }
    if thread_message_id:
        payload["headers"] = {
            "In-Reply-To": thread_message_id,
            "References": thread_message_id,
        }
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"terrasatch-workspace-email/{request_id}"[:256],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers=headers,
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderUnavailable("Resend workspace email delivery failed") from error
    if not isinstance(data, dict):
        raise ProviderUnavailable("Resend workspace email response is invalid")
    provider_id = str(data.get("id") or "").strip()
    if not provider_id:
        raise ProviderUnavailable("Resend workspace email response is missing an email ID")
    message_id = str(data.get("message_id") or "").strip() or None
    return provider_id[:255], message_id[:1024] if message_id else None


async def send_workspace_email(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    role: MembershipRole,
    sender: str,
    recipients: list[str],
    subject: str,
    text: str,
    request_id: UUID,
    parent_email_id: UUID | None = None,
    thread_message_id: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> WorkspaceEmailMessage:
    normalized_sender = normalize_email_address(sender)
    allowed = await sendable_mailboxes(session, user=user, role=role)
    if normalized_sender not in allowed:
        raise InvalidConfiguration("You are not allowed to send from this TerraSatch mailbox")

    clean_recipients = [normalize_email_address(item) for item in recipients]
    if not clean_recipients or any(not item for item in clean_recipients):
        raise InvalidConfiguration("One or more recipient email addresses are invalid")

    provider_id, provider_message_id = await _post_resend_email(
        settings,
        sender=normalized_sender,
        recipients=clean_recipients,
        subject=subject,
        text=text,
        request_id=request_id,
        thread_message_id=thread_message_id,
        transport=transport,
    )
    existing = await session.scalar(
        select(WorkspaceEmailMessage).where(
            WorkspaceEmailMessage.provider_email_id == provider_id
        )
    )
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    row = WorkspaceEmailMessage(
        provider_email_id=provider_id,
        direction="outbound",
        parent_email_id=parent_email_id,
        recipient_user_id=user.id,
        internet_message_id=provider_message_id,
        received_for=normalized_sender,
        from_address=normalized_sender,
        to_addresses=clean_recipients,
        cc_addresses=[],
        bcc_addresses=[],
        reply_to=[],
        subject=subject.strip(),
        text_body=text.strip(),
        html_body=None,
        headers=(
            {"In-Reply-To": thread_message_id, "References": thread_message_id}
            if thread_message_id
            else {}
        ),
        attachments=[],
        received_at=now,
    )
    session.add(row)
    await session.flush()
    await mark_workspace_email_read(session, user=user, email_id=row.id)
    return row


async def reply_to_workspace_email(
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    role: MembershipRole,
    email_id: UUID,
    text: str,
    request_id: UUID,
    transport: httpx.AsyncBaseTransport | None = None,
) -> WorkspaceEmailMessage:
    original = await get_workspace_email(
        session,
        user=user,
        role=role,
        email_id=email_id,
    )
    if original.direction != "inbound":
        raise InvalidConfiguration("Only inbound email can be replied to")
    sender = normalize_email_address(original.received_for)
    if sender not in await sendable_mailboxes(session, user=user, role=role):
        raise InvalidConfiguration("This mailbox is view-only for your account")
    reply_target = (
        original.reply_to[0]
        if original.reply_to
        else original.from_address
    )
    recipient = normalize_email_address(reply_target)
    if not recipient:
        raise InvalidConfiguration("The original sender address is invalid")
    subject = original.subject.strip()
    if not subject.casefold().startswith("re:"):
        subject = f"Re: {subject or '(no subject)'}"
    return await send_workspace_email(
        session,
        settings,
        user=user,
        role=role,
        sender=sender,
        recipients=[recipient],
        subject=subject,
        text=text,
        request_id=request_id,
        parent_email_id=original.id,
        thread_message_id=original.internet_message_id,
        transport=transport,
    )
