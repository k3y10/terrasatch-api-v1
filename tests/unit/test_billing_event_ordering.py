from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import hash_admin_password
from terrasatch.billing.models import BillingCustomer, BillingSignup, Subscription
from terrasatch.billing.service import (
    _mark_invoice_failed,
    _mark_invoice_paid,
    sync_subscription_snapshot,
)
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import (
    Account,
    Membership,
    MembershipRole,
    Organization,
    User,
)


def settings() -> Settings:
    return Settings(billing_activation_signing_secret="test-event-ordering-secret")


async def seed_billing_state(session):
    now = datetime.now(UTC)
    account = Account(id=uuid4(), name="Ordering Test")
    organization = Organization(
        id=uuid4(),
        account_id=account.id,
        name="Ordering Org",
        slug=f"ordering-{uuid4().hex[:8]}",
    )
    user = User(
        id=uuid4(),
        email="ordering@example.com",
        display_name="Ordering Owner",
        password_hash=hash_admin_password("existing-password-123"),
        credential_version=1,
    )
    membership = Membership(
        id=uuid4(),
        organization_id=organization.id,
        user_id=user.id,
        role=MembershipRole.OWNER,
    )
    signup = BillingSignup(
        id=uuid4(),
        email=user.email,
        display_name=user.display_name,
        organization_name=organization.name,
        plan_code="field",
        billing_interval="monthly",
        status="completed",
        stripe_customer_id="cus_ordering",
        expires_at=now + timedelta(hours=1),
        completed_at=now,
    )
    customer = BillingCustomer(
        id=uuid4(),
        account_id=account.id,
        organization_id=organization.id,
        stripe_customer_id="cus_ordering",
    )
    subscription = Subscription(
        id=uuid4(),
        organization_id=organization.id,
        billing_customer_id=customer.id,
        stripe_subscription_id="sub_ordering",
        stripe_price_id="price_ordering",
        plan_code="field",
        billing_interval="monthly",
        status="active",
        cancel_at_period_end=False,
        last_subscription_event_created=200,
        last_invoice_event_created=200,
    )
    session.add_all(
        [
            account,
            organization,
            user,
            membership,
            signup,
            customer,
            subscription,
        ]
    )
    await session.flush()
    return signup, subscription


def subscription_snapshot(signup_id, *, status: str, cancel_at_period_end: bool):
    return {
        "id": "sub_ordering",
        "customer": "cus_ordering",
        "status": status,
        "cancel_at_period_end": cancel_at_period_end,
        "metadata": {
            "signup_id": str(signup_id),
            "plan_code": "field",
            "billing_interval": "monthly",
        },
        "items": {
            "data": [
                {
                    "quantity": 1,
                    "price": {
                        "id": "price_ordering",
                        "lookup_key": "terrasatch_individual_monthly_v2",
                        "unit_amount": 2400,
                        "currency": "usd",
                        "recurring": {
                            "interval": "month",
                            "interval_count": 1,
                        },
                    },
                }
            ]
        },
    }


@pytest.mark.asyncio
async def test_stale_subscription_snapshot_cannot_overwrite_newer_state() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        signup, subscription = await seed_billing_state(session)

        stale = await sync_subscription_snapshot(
            session,
            snapshot=subscription_snapshot(
                signup.id,
                status="canceled",
                cancel_at_period_end=True,
            ),
            settings=settings(),
            event_created=100,
        )
        assert stale.state_applied is False
        assert subscription.status == "active"
        assert subscription.cancel_at_period_end is False
        assert subscription.last_subscription_event_created == 200

        current = await sync_subscription_snapshot(
            session,
            snapshot=subscription_snapshot(
                signup.id,
                status="active",
                cancel_at_period_end=True,
            ),
            settings=settings(),
            event_created=300,
        )
        assert current.state_applied is True
        assert subscription.status == "active"
        assert subscription.cancel_at_period_end is True
        assert subscription.last_subscription_event_created == 300

    await engine.dispose()


@pytest.mark.asyncio
async def test_stale_invoice_events_cannot_reverse_newer_payment_state() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        _signup, subscription = await seed_billing_state(session)

        organization_id, applied = await _mark_invoice_failed(
            session,
            invoice={"id": "in_stale_failed", "subscription": "sub_ordering"},
            settings=settings(),
            event_created=100,
        )
        assert organization_id == subscription.organization_id
        assert applied is False
        assert subscription.status == "active"
        assert subscription.last_invoice_event_created == 200

        _organization_id, applied = await _mark_invoice_failed(
            session,
            invoice={"id": "in_current_failed", "subscription": "sub_ordering"},
            settings=settings(),
            event_created=300,
        )
        assert applied is True
        assert subscription.status == "past_due"
        assert subscription.last_invoice_event_created == 300

        _organization_id, applied = await _mark_invoice_paid(
            session,
            invoice={"id": "in_stale_paid", "subscription": "sub_ordering"},
            event_created=250,
        )
        assert applied is False
        assert subscription.status == "past_due"
        assert subscription.last_invoice_event_created == 300

        _organization_id, applied = await _mark_invoice_paid(
            session,
            invoice={"id": "in_current_paid", "subscription": "sub_ordering"},
            event_created=400,
        )
        assert applied is True
        assert subscription.status == "active"
        assert subscription.last_invoice_event_created == 400

    await engine.dispose()
