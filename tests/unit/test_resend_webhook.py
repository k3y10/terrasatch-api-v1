from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.billing.models import BillingEmailOutbox
from terrasatch.billing.resend_webhook import (
    reconcile_resend_webhook,
    verify_resend_webhook,
)
from terrasatch.database.base import Base
from terrasatch.errors import InvalidConfiguration


SECRET_BYTES = b"terrasatch-resend-webhook-test"
SECRET = SecretStr(
    "whsec_" + base64.b64encode(SECRET_BYTES).decode("ascii")
)


def signed_headers(
    payload: bytes,
    *,
    webhook_id: str = "msg_test_1",
    timestamp: int | None = None,
) -> dict[str, str]:
    timestamp = timestamp or int(datetime.now(UTC).timestamp())
    timestamp_text = str(timestamp)
    signed = f"{webhook_id}.{timestamp_text}.".encode() + payload
    signature = base64.b64encode(
        hmac.new(SECRET_BYTES, signed, hashlib.sha256).digest()
    ).decode("ascii")
    return {
        "svix-id": webhook_id,
        "svix-timestamp": timestamp_text,
        "svix-signature": f"v1,{signature}",
    }


def test_verify_resend_webhook_accepts_valid_raw_body_signature() -> None:
    payload = (
        b'{"type":"email.delivered","created_at":"2026-09-18T18:00:00Z",'
        b'"data":{"email_id":"email_123"}}'
    )
    event, webhook_id = verify_resend_webhook(
        raw_payload=payload,
        headers=signed_headers(payload),
        secret=SECRET,
    )

    assert webhook_id == "msg_test_1"
    assert event["type"] == "email.delivered"


def test_verify_resend_webhook_rejects_stale_or_invalid_signatures() -> None:
    payload = b'{"type":"email.delivered","data":{"email_id":"email_123"}}'
    stale = int(datetime.now(UTC).timestamp()) - 301

    with pytest.raises(InvalidConfiguration):
        verify_resend_webhook(
            raw_payload=payload,
            headers=signed_headers(payload, timestamp=stale),
            secret=SECRET,
        )

    headers = signed_headers(payload)
    headers["svix-signature"] = "v1,not-a-valid-signature"
    with pytest.raises(InvalidConfiguration):
        verify_resend_webhook(
            raw_payload=payload,
            headers=headers,
            secret=SECRET,
        )


@pytest.mark.asyncio
async def test_reconcile_resend_webhook_tracks_delivery_and_bounce() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)

    async with factory() as session:
        session.add_all(
            [
                BillingEmailOutbox(
                    event_id="evt_delivered",
                    kind="trial_started",
                    context={},
                    attempts=1,
                    next_attempt_at=now,
                    first_attempt_at=now,
                    sent_at=now,
                    delivery_provider="resend",
                    provider_message_id="email_delivered",
                    delivery_status="accepted",
                ),
                BillingEmailOutbox(
                    event_id="evt_bounced",
                    kind="trial_ending",
                    context={},
                    attempts=1,
                    next_attempt_at=now,
                    first_attempt_at=now,
                    sent_at=now,
                    delivery_provider="resend",
                    provider_message_id="email_bounced",
                    delivery_status="accepted",
                ),
            ]
        )
        await session.commit()

        delivered = await reconcile_resend_webhook(
            session,
            event={
                "type": "email.delivered",
                "created_at": "2026-09-18T18:00:00Z",
                "data": {"email_id": "email_delivered"},
            },
            webhook_id="msg_delivered",
        )
        await session.commit()

        assert delivered.matched is True
        assert delivered.duplicate is False

        row = await session.get(BillingEmailOutbox, "evt_delivered")
        assert row is not None
        assert row.delivery_status == "delivered"
        assert row.delivered_at is not None
        assert row.provider_event_id == "msg_delivered"
        assert row.last_error is None

        duplicate = await reconcile_resend_webhook(
            session,
            event={
                "type": "email.delivered",
                "data": {"email_id": "email_delivered"},
            },
            webhook_id="msg_delivered",
        )
        assert duplicate.duplicate is True

        bounced = await reconcile_resend_webhook(
            session,
            event={
                "type": "email.bounced",
                "data": {"email_id": "email_bounced"},
            },
            webhook_id="msg_bounced",
        )
        await session.commit()

        assert bounced.matched is True
        bounce_row = await session.get(BillingEmailOutbox, "evt_bounced")
        assert bounce_row is not None
        assert bounce_row.delivery_status == "bounced"
        assert bounce_row.last_error == "resend_bounced"

    await engine.dispose()


@pytest.mark.asyncio
async def test_reconcile_resend_webhook_ignores_unmatched_email_ids() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        result = await reconcile_resend_webhook(
            session,
            event={
                "type": "email.delivered",
                "data": {"email_id": "email_not_billing"},
            },
            webhook_id="msg_unmatched",
        )

    assert result.matched is False
    await engine.dispose()
