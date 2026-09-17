from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.billing.models import BillingEmailOutbox
from terrasatch.billing.notifications import BillingEmailContext
from terrasatch.billing.outbox import dispatch_email_batch, enqueue_email
from terrasatch.billing.plans import BillingInterval, get_plan
from terrasatch.billing.service import recover_activation_token
from terrasatch.billing.stripe_gateway import validate_price
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable


def settings():
    return Settings(billing_activation_signing_secret="a-test-signing-secret")


def context():
    return BillingEmailContext(
        "owner@example.com", "Owner", "Org", "Individual", "monthly", 2400, None, None, None, False
    )


@pytest.mark.asyncio
async def test_rollback_cannot_send_and_retry_keeps_identical_payload(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    deliveries = []

    async def send(**kwargs):
        deliveries.append((kwargs["event_id"], asdict(kwargs["context"])))
        if len(deliveries) == 1:
            raise ProviderUnavailable("temporary")
        return True

    monkeypatch.setattr("terrasatch.billing.outbox.deliver_billing_email", send)
    async with factory() as session:
        await enqueue_email(session, event_id="rolled-back", kind="trial_ending", context=context())
        await session.rollback()
    assert await dispatch_email_batch(settings(), session_factory=factory) == 0
    assert deliveries == []
    async with factory() as session:
        await enqueue_email(session, event_id="committed", kind="trial_ending", context=context())
        await session.commit()
    assert await dispatch_email_batch(settings(), session_factory=factory) == 0
    async with factory() as session:
        row = await session.get(BillingEmailOutbox, "committed")
        assert row.attempts == 1 and row.first_attempt_at is not None
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert await dispatch_email_batch(settings(), session_factory=factory) == 1
    assert deliveries[0] == deliveries[1]
    assert await dispatch_email_batch(settings(), session_factory=factory) == 0
    await engine.dispose()


def test_activation_recovery_is_stable_and_requires_the_secret():
    identity = uuid4()
    assert recover_activation_token(settings(), identity) == recover_activation_token(
        settings(), identity
    )
    assert recover_activation_token(settings(), identity) != recover_activation_token(
        settings(), uuid4()
    )
    with pytest.raises(InvalidConfiguration):
        recover_activation_token(Settings(), identity)


@pytest.mark.parametrize(
    "patch",
    [
        {"unit_amount": 99},
        {"currency": "eur"},
        {"lookup_key": "wrong"},
        {"recurring": {"interval": "year", "interval_count": 1}},
    ],
)
def test_price_integrity_rejects_wrong_amount_currency_key_and_cadence(patch):
    price = {
        "id": "price_test",
        "unit_amount": 2400,
        "currency": "usd",
        "lookup_key": "terrasatch_individual_monthly_v2",
        "recurring": {"interval": "month", "interval_count": 1},
    }
    validate_price(price, get_plan("field"), BillingInterval.MONTHLY)
    price.update(patch)
    with pytest.raises(InvalidConfiguration):
        validate_price(price, get_plan("field"), BillingInterval.MONTHLY)


@pytest.mark.parametrize(
    "missing",
    [
        "billing_email_webhook_url",
        "billing_email_webhook_secret",
        "billing_activation_signing_secret",
        "stripe_secret_key",
        "stripe_webhook_secret",
    ],
)
def test_readiness_requires_every_dependency(missing):
    values = dict(
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/email",
        billing_email_webhook_secret="test",
        billing_activation_signing_secret="test",
        stripe_secret_key="test",
        stripe_webhook_secret="test",
    )
    assert Settings(**values).billing_is_configured
    values[missing] = None
    assert not Settings(**values).billing_is_configured
