"""One-time, idempotent import of the stranded workspace-email staging bundle."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.errors import InvalidConfiguration
from terrasatch.identity.models import User
from terrasatch.workspace.email_models import (
    WorkspaceEmailDelegate,
    WorkspaceEmailMessage,
    WorkspaceEmailRead,
)
from terrasatch.workspace.email_service import normalize_email_address


def _datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise InvalidConfiguration(f"Recovery bundle is missing {field}")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidConfiguration(f"Recovery bundle has invalid {field}") from error


def _uuid(value: object) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except ValueError as error:
        raise InvalidConfiguration("Recovery bundle contains an invalid UUID") from error


def _records(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise InvalidConfiguration(f"Recovery bundle field {key} must be a list of objects")
    return value


async def import_workspace_email_bundle(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, int]:
    """Import one staging export while remapping user ownership by email address."""

    if payload.get("version") != 1:
        raise InvalidConfiguration("Unsupported workspace email recovery bundle version")

    users = _records(payload, "users")
    messages = _records(payload, "messages")
    reads = _records(payload, "reads")
    delegates = _records(payload, "delegates")

    staging_user_email: dict[UUID, str] = {}
    for item in users:
        user_id = _uuid(item.get("id"))
        email = normalize_email_address(str(item.get("email") or ""))
        if user_id is not None and email:
            staging_user_email[user_id] = email

    production_users = {
        user.email.casefold(): user
        for user in await session.scalars(select(User).where(User.enabled.is_(True)))
    }

    missing_user_emails: set[str] = set()

    def mapped_user_id(
        staging_user_id: object,
        *,
        mailbox: object | None = None,
    ) -> UUID | None:
        source_id = _uuid(staging_user_id)
        email = staging_user_email.get(source_id) if source_id is not None else None
        if not email and mailbox is not None:
            candidate = normalize_email_address(str(mailbox or ""))
            if candidate in production_users:
                email = candidate
        if not email:
            return None
        user = production_users.get(email.casefold())
        if user is None:
            missing_user_emails.add(email)
            return None
        return user.id

    existing_by_provider = {
        row.provider_email_id: row
        for row in await session.scalars(select(WorkspaceEmailMessage))
    }
    old_to_new: dict[UUID, UUID] = {}
    pending_parent: list[tuple[WorkspaceEmailMessage, UUID | None]] = []
    created_messages = 0
    skipped_messages = 0

    for item in messages:
        old_id = _uuid(item.get("id"))
        provider_email_id = str(item.get("provider_email_id") or "").strip()
        if old_id is None or not provider_email_id:
            raise InvalidConfiguration("Recovery message is missing id/provider_email_id")

        existing = existing_by_provider.get(provider_email_id)
        if existing is not None:
            old_to_new[old_id] = existing.id
            skipped_messages += 1
            continue

        parent_old_id = _uuid(item.get("parent_email_id"))
        row = WorkspaceEmailMessage(
            provider_email_id=provider_email_id,
            provider_event_id=(
                str(item["provider_event_id"])
                if item.get("provider_event_id") is not None
                else None
            ),
            direction=str(item.get("direction") or "inbound"),
            parent_email_id=None,
            recipient_user_id=mapped_user_id(
                item.get("recipient_user_id"),
                mailbox=item.get("received_for"),
            ),
            internet_message_id=(
                str(item["internet_message_id"])
                if item.get("internet_message_id") is not None
                else None
            ),
            received_for=str(item.get("received_for") or ""),
            from_address=str(item.get("from_address") or ""),
            to_addresses=list(item.get("to_addresses") or []),
            cc_addresses=list(item.get("cc_addresses") or []),
            bcc_addresses=list(item.get("bcc_addresses") or []),
            reply_to=list(item.get("reply_to") or []),
            subject=str(item.get("subject") or ""),
            text_body=(
                str(item["text_body"]) if item.get("text_body") is not None else None
            ),
            html_body=(
                str(item["html_body"]) if item.get("html_body") is not None else None
            ),
            headers=dict(item.get("headers") or {}),
            attachments=list(item.get("attachments") or []),
            received_at=_datetime(item.get("received_at"), field="received_at"),
            created_at=_datetime(item.get("created_at"), field="created_at"),
            updated_at=_datetime(item.get("updated_at"), field="updated_at"),
        )
        if not dry_run:
            session.add(row)
            await session.flush()
            old_to_new[old_id] = row.id
            pending_parent.append((row, parent_old_id))
        else:
            old_to_new[old_id] = old_id
        created_messages += 1

    if not dry_run:
        for row, parent_old_id in pending_parent:
            if parent_old_id is not None:
                row.parent_email_id = old_to_new.get(parent_old_id)
        await session.flush()

    created_reads = 0
    skipped_reads = 0
    for item in reads:
        old_email_id = _uuid(item.get("email_id"))
        new_email_id = old_to_new.get(old_email_id) if old_email_id is not None else None
        user_id = mapped_user_id(item.get("user_id"))
        if new_email_id is None or user_id is None:
            continue
        existing = await session.get(
            WorkspaceEmailRead,
            {"email_id": new_email_id, "user_id": user_id},
        )
        if existing is not None:
            skipped_reads += 1
            continue
        created_reads += 1
        if not dry_run:
            session.add(
                WorkspaceEmailRead(
                    email_id=new_email_id,
                    user_id=user_id,
                    read_at=_datetime(item.get("read_at"), field="read_at"),
                )
            )

    created_delegates = 0
    skipped_delegates = 0
    for item in delegates:
        mailbox = normalize_email_address(str(item.get("mailbox_address") or ""))
        user_id = mapped_user_id(item.get("user_id"))
        if not mailbox or user_id is None:
            continue
        existing = await session.scalar(
            select(WorkspaceEmailDelegate).where(
                WorkspaceEmailDelegate.mailbox_address == mailbox,
                WorkspaceEmailDelegate.user_id == user_id,
            )
        )
        if existing is not None:
            skipped_delegates += 1
            continue
        created_delegates += 1
        if not dry_run:
            session.add(
                WorkspaceEmailDelegate(
                    mailbox_address=mailbox,
                    user_id=user_id,
                    can_send=bool(item.get("can_send")),
                    created_by_user_id=mapped_user_id(item.get("created_by_user_id")),
                    created_at=_datetime(item.get("created_at"), field="created_at"),
                    updated_at=_datetime(item.get("updated_at"), field="updated_at"),
                )
            )

    if missing_user_emails:
        missing = ", ".join(sorted(missing_user_emails))
        raise InvalidConfiguration(
            f"Recovery bundle references users not present in production: {missing}"
        )

    if not dry_run:
        await session.flush()

    return {
        "messages_created": created_messages,
        "messages_skipped": skipped_messages,
        "reads_created": created_reads,
        "reads_skipped": skipped_reads,
        "delegates_created": created_delegates,
        "delegates_skipped": skipped_delegates,
    }
