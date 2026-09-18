from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import verify_admin_password
from terrasatch.billing.service import recover_or_refresh_activation_for_email
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import (
    Account,
    Membership,
    MembershipRole,
    Organization,
    PasswordResetIntent,
    User,
)
from terrasatch.identity.recovery import (
    create_password_reset_intent,
    recover_password_reset_token,
    reset_password,
)


def settings() -> Settings:
    return Settings(
        billing_activation_signing_secret=SecretStr("test-account-recovery-secret"),
        account_password_reset_ttl_minutes=30,
    )


async def seed_account(session):
    account = Account(id=uuid4(), name="Recovery Test")
    organization = Organization(
        id=uuid4(),
        account_id=account.id,
        name="Recovery Org",
        slug=f"recovery-{uuid4().hex[:8]}",
    )
    user = User(
        id=uuid4(),
        email="owner@example.com",
        display_name="Owner",
    )
    membership = Membership(
        id=uuid4(),
        organization_id=organization.id,
        user_id=user.id,
        role=MembershipRole.OWNER,
    )
    session.add_all([account, organization, user, membership])
    await session.flush()
    return organization, user


@pytest.mark.asyncio
async def test_password_reset_is_single_use_and_replaces_password() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        organization, user = await seed_account(session)
        intent = await create_password_reset_intent(
            session,
            email=user.email,
            settings=settings(),
        )
        assert intent is not None
        token = recover_password_reset_token(settings(), intent.id)
        assert hashlib.sha256(token.encode()).hexdigest() == intent.token_hash

        reset_user = await reset_password(
            session,
            token=token,
            password="new-password-123",
        )
        assert reset_user.id == user.id
        assert verify_admin_password("new-password-123", reset_user.password_hash or "")
        await session.commit()

        stored = await session.get(PasswordResetIntent, intent.id)
        assert stored is not None
        assert stored.consumed_at is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_new_password_reset_invalidates_previous_intent() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        _organization, user = await seed_account(session)
        first = await create_password_reset_intent(
            session,
            email=user.email,
            settings=settings(),
        )
        second = await create_password_reset_intent(
            session,
            email=user.email,
            settings=settings(),
        )
        assert first is not None and second is not None
        await session.flush()
        first_stored = await session.get(PasswordResetIntent, first.id)
        assert first_stored is not None
        assert first_stored.consumed_at is not None
        assert second.consumed_at is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_activation_resend_reuses_valid_activation() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        organization, user = await seed_account(session)
        first = await recover_or_refresh_activation_for_email(
            session,
            email=user.email,
            settings=settings(),
        )
        second = await recover_or_refresh_activation_for_email(
            session,
            email=user.email,
            settings=settings(),
        )
        assert first is not None
        assert second == first
        assert first[1] == organization.id

    await engine.dispose()
