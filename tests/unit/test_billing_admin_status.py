from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.commands_v2 import run_admin_command
from terrasatch.billing.models import BillingEmailOutbox
from terrasatch.database.base import Base


@pytest.mark.asyncio
async def test_billing_email_status_reports_delivery_receipts_without_context() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        now = datetime.now(UTC)
        session.add_all(
            [
                BillingEmailOutbox(
                    event_id="evt_sent",
                    kind="trial_started",
                    context={"to": "hidden@example.com"},
                    attempts=1,
                    next_attempt_at=now,
                    first_attempt_at=now,
                    sent_at=now,
                    delivery_provider="resend",
                    provider_message_id="email_123",
                ),
                BillingEmailOutbox(
                    event_id="evt_retry",
                    kind="payment_failed",
                    context={"to": "hidden2@example.com"},
                    attempts=2,
                    next_attempt_at=now,
                    first_attempt_at=now,
                    last_error="delivery_failed",
                ),
            ]
        )
        await session.commit()

        result = await run_admin_command(
            session,
            command="billing email-status",
            selected_organization=None,
        )

    text = "\n".join(result.lines)
    assert "sent=1" in text
    assert "retrying=1" in text
    assert "resend" in text
    assert "email_123" in text
    assert "hidden@example.com" not in text
    assert "hidden2@example.com" not in text
    await engine.dispose()
