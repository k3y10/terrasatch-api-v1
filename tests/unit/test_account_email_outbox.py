from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import terrasatch.billing.outbox as outbox
from terrasatch.admin.security import hash_admin_password
from terrasatch.billing.models import BillingEmailOutbox
from terrasatch.billing.notifications import (
    BillingEmailDeliveryReceipt,
    get_account_email_context,
)
from terrasatch.billing.outbox import dispatch_email_batch, enqueue_email
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import Account, Membership, MembershipRole, Organization, User
from terrasatch.identity.recovery import create_password_reset_intent


@pytest.mark.asyncio
async def test_password_reset_outbox_reconstructs_link_without_storing_token(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        api_base_url="https://staging-api.terrasatch.com",
        billing_activation_signing_secret=SecretStr("test-account-recovery-secret"),
        resend_api_key=SecretStr("re_test"),
        billing_from="TerraSatch Billing <billing@terrasatch.com>",
    )

    async with factory() as session:
        account = Account(id=uuid4(), name="Outbox Test")
        organization = Organization(
            id=uuid4(),
            account_id=account.id,
            name="Outbox Org",
            slug=f"outbox-{uuid4().hex[:8]}",
        )
        user = User(
            id=uuid4(),
            email="owner@example.com",
            display_name="Owner",
            password_hash=hash_admin_password("existing-password-123"),
            credential_version=1,
        )
        membership = Membership(
            id=uuid4(),
            organization_id=organization.id,
            user_id=user.id,
            role=MembershipRole.OWNER,
        )
        session.add_all([account, organization, user, membership])
        await session.flush()

        reset = await create_password_reset_intent(
            session,
            email=user.email,
            settings=settings,
        )
        assert reset is not None
        context = await get_account_email_context(session, user_id=user.id)
        assert context is not None
        await enqueue_email(
            session,
            event_id=f"account:password-reset:{reset.id}",
            kind="password_reset",
            context=context,
            password_reset_id=reset.id,
        )
        await session.commit()

    captured: dict[str, object] = {}

    async def fake_delivery(**kwargs):
        captured.update(kwargs)
        return BillingEmailDeliveryReceipt(provider="resend", message_id="email_reset_1")

    monkeypatch.setattr(outbox, "deliver_billing_email", fake_delivery)

    sent = await dispatch_email_batch(settings, session_factory=factory, limit=1)
    assert sent == 1
    assert captured["kind"] == "password_reset"
    assert str(captured["action_url"]).startswith(
        "https://staging-api.terrasatch.com/portal/reset-password#token="
    )

    async with factory() as session:
        row = await session.get(
            BillingEmailOutbox,
            f"account:password-reset:{reset.id}",
        )
        assert row is not None
        assert row.delivery_status == "accepted"
        assert row.provider_message_id == "email_reset_1"
        assert "token" not in str(row.context).casefold()

    await engine.dispose()
