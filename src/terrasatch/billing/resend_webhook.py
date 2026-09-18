"""Signature verification and reconciliation for Resend delivery webhooks."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.billing.models import BillingEmailOutbox
from terrasatch.errors import InvalidConfiguration


_ALLOWED_EVENTS = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delivery_delayed",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.failed": "failed",
    "email.suppressed": "suppressed",
}
_TERMINAL_FAILURES = {"bounced", "complained", "failed", "suppressed"}
_SIGNATURE_TOLERANCE_SECONDS = 300


@dataclass(frozen=True, slots=True)
class ResendWebhookResult:
    matched: bool
    duplicate: bool
    event_type: str


def _header(headers: Mapping[str, str], *names: str) -> str:
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    raise InvalidConfiguration(f"Missing Resend webhook header: {names[0]}")


def _decode_webhook_secret(secret: SecretStr) -> bytes:
    raw = secret.get_secret_value().strip()
    encoded = raw.removeprefix("whsec_")
    if not encoded:
        raise InvalidConfiguration("Resend webhook signing secret is empty")
    padded = encoded + ("=" * (-len(encoded) % 4))
    try:
        return base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise InvalidConfiguration("Resend webhook signing secret is invalid") from error


def verify_resend_webhook(
    *,
    raw_payload: bytes,
    headers: Mapping[str, str],
    secret: SecretStr,
    now: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    """Verify a Resend/Svix raw-body signature with five-minute replay tolerance."""

    webhook_id = _header(headers, "svix-id", "webhook-id")
    timestamp_text = _header(headers, "svix-timestamp", "webhook-timestamp")
    signature_header = _header(headers, "svix-signature", "webhook-signature")

    try:
        timestamp = int(timestamp_text)
    except ValueError as error:
        raise InvalidConfiguration("Resend webhook timestamp is invalid") from error

    current = now or datetime.now(UTC)
    if abs(int(current.timestamp()) - timestamp) > _SIGNATURE_TOLERANCE_SECONDS:
        raise InvalidConfiguration("Resend webhook timestamp is outside the allowed window")

    signed_content = (
        f"{webhook_id}.{timestamp_text}.".encode("utf-8") + raw_payload
    )
    expected = base64.b64encode(
        hmac.new(
            _decode_webhook_secret(secret),
            signed_content,
            hashlib.sha256,
        ).digest()
    ).decode("ascii")

    valid = False
    for item in signature_header.split():
        version, separator, signature = item.partition(",")
        if separator and version == "v1" and hmac.compare_digest(signature, expected):
            valid = True
            break
    if not valid:
        raise InvalidConfiguration("Resend webhook signature is invalid")

    try:
        event = json.loads(raw_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidConfiguration("Resend webhook payload is invalid JSON") from error
    if not isinstance(event, dict):
        raise InvalidConfiguration("Resend webhook payload must be an object")
    return event, webhook_id


def _event_time(event: dict[str, Any]) -> datetime:
    value = event.get("created_at")
    if not isinstance(value, str):
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def reconcile_resend_webhook(
    session: AsyncSession,
    *,
    event: dict[str, Any],
    webhook_id: str,
) -> ResendWebhookResult:
    """Apply one verified Resend delivery event to a matching billing outbox row."""

    event_type = str(event.get("type") or "")
    delivery_status = _ALLOWED_EVENTS.get(event_type)
    if delivery_status is None:
        return ResendWebhookResult(
            matched=False,
            duplicate=False,
            event_type=event_type,
        )

    data = event.get("data")
    email_id = str(data.get("email_id") or "") if isinstance(data, dict) else ""
    if not email_id:
        raise InvalidConfiguration("Resend email event is missing data.email_id")

    row = await session.scalar(
        select(BillingEmailOutbox)
        .where(BillingEmailOutbox.provider_message_id == email_id)
        .with_for_update()
    )
    if row is None:
        return ResendWebhookResult(
            matched=False,
            duplicate=False,
            event_type=event_type,
        )
    if row.provider_event_id == webhook_id:
        return ResendWebhookResult(
            matched=True,
            duplicate=True,
            event_type=event_type,
        )

    occurred_at = _event_time(event)
    row.provider_event_id = webhook_id
    row.provider_event_at = occurred_at
    row.delivery_status = delivery_status

    if delivery_status == "delivered":
        row.delivered_at = occurred_at
        row.last_error = None
    elif delivery_status in _TERMINAL_FAILURES:
        row.last_error = f"resend_{delivery_status}"

    await session.flush()
    return ResendWebhookResult(
        matched=True,
        duplicate=False,
        event_type=event_type,
    )
