from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.billing.models import BillingSignup
from terrasatch.billing.schemas import CheckoutRequest
from terrasatch.billing.service import _provision_signup, _sync_checkout_completed, create_signup
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.errors import ResourceConflict
from terrasatch.identity.models import Site


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="billing-signup-service-test",
        billing_checkout_ttl_minutes=120,
    )


def checkout_request(*, plan_code: str = "team") -> CheckoutRequest:
    return CheckoutRequest(
        display_name="Test Operator",
        email="operator@example.com",
        organization_name="Example Mountain Ops",
        plan_code=plan_code,
        billing_interval="monthly",
    )


@pytest.mark.asyncio
async def test_signup_provisions_one_usable_site_and_retry_does_not_duplicate():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    configured = Settings(billing_activation_signing_secret="test-only-activation-secret")
    async with sessions() as session:
        signup = await create_signup(session, payload=checkout_request(), settings=configured)
        first = await _provision_signup(
            session, signup=signup, stripe_customer_id="cus_site_test", settings=configured
        )
        await session.commit()
        repeated = await _provision_signup(
            session, signup=signup, stripe_customer_id="cus_site_test", settings=configured
        )
        await session.commit()
        sites = list(await session.scalars(select(Site)))
        assert repeated.organization_id == first.organization_id
        assert len(sites) == 1
        assert sites[0].organization_id == first.organization_id
        assert sites[0].enabled and sites[0].name == signup.organization_name
    await engine.dispose()


@pytest.mark.asyncio
async def test_unexpired_signup_is_resumed_for_stripe_idempotency() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        first = await create_signup(
            session,
            payload=checkout_request(),
            settings=make_settings(),
        )
        await session.commit()

        resumed = await create_signup(
            session,
            payload=checkout_request(),
            settings=make_settings(),
        )

        assert resumed.id == first.id
        assert resumed.status == "pending"

    await engine.dispose()


@pytest.mark.asyncio
async def test_active_signup_rejects_plan_change() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        await create_signup(
            session,
            payload=checkout_request(plan_code="team"),
            settings=make_settings(),
        )
        await session.commit()

        with pytest.raises(ResourceConflict, match="active TerraSatch Checkout"):
            await create_signup(
                session,
                payload=checkout_request(plan_code="field"),
                settings=make_settings(),
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_expired_signup_is_replaced_with_new_attempt() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        first = await create_signup(
            session,
            payload=checkout_request(),
            settings=make_settings(),
        )
        first.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        first_id = first.id

        replacement = await create_signup(
            session,
            payload=checkout_request(),
            settings=make_settings(),
        )
        await session.commit()
        expired = await session.get(BillingSignup, first_id)

        assert replacement.id != first_id
        assert expired is not None
        assert expired.status == "expired"

    await engine.dispose()


@pytest.mark.asyncio
async def test_completed_trial_blocks_repeat_self_service_trial() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        signup = await create_signup(
            session,
            payload=checkout_request(),
            settings=make_settings(),
        )
        signup.status = "completed"
        await session.commit()

        with pytest.raises(ResourceConflict, match="trial already exists"):
            await create_signup(
                session,
                payload=checkout_request(),
                settings=make_settings(),
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_payment_link_checkout_provisions_before_subscription_event() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    configured = Settings(billing_activation_signing_secret="test-only-activation-secret")

    async with sessions() as session:
        signup = await create_signup(
            session,
            payload=checkout_request(plan_code="field"),
            settings=configured,
        )
        await session.commit()

        result = await _sync_checkout_completed(
            session,
            checkout={
                "id": "cs_test_payment_link",
                "customer": "cus_payment_link",
                "client_reference_id": str(signup.id),
                "customer_details": {"email": signup.email},
            },
            subscription_snapshot=None,
            settings=configured,
        )
        await session.commit()
        refreshed = await session.get(BillingSignup, signup.id)

        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.stripe_checkout_session_id == "cs_test_payment_link"
        assert refreshed.stripe_customer_id == "cus_payment_link"
        assert result.organization_id is not None
        assert result.activation_token is not None

    await engine.dispose()
