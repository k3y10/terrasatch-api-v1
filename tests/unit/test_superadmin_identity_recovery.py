"""Recovered unified founder identity behavior."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import hash_admin_password, verify_admin_password
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.access import (
    establish_browser_identity,
    promote_superadmin_identity,
)
from terrasatch.identity.models import Account, MembershipRole, Organization, User


def test_superadmin_browser_identity_unlocks_admin_and_portal() -> None:
    user = User(
        id=uuid4(),
        email="keaton@terrasatch.com",
        display_name="Keaton",
        password_hash=hash_admin_password("founder-password-123"),
        credential_version=4,
        is_superadmin=True,
        enabled=True,
    )
    session: dict[str, object] = {}

    establish_browser_identity(session, user)

    assert session["portal_user_id"] == str(user.id)
    assert session["portal_email"] == "keaton@terrasatch.com"
    assert session["portal_credential_version"] == 4
    assert session["admin_authenticated"] is True


def test_normal_browser_identity_does_not_unlock_admin() -> None:
    user = User(
        id=uuid4(),
        email="member@terrasatch.com",
        display_name="Member",
        password_hash=hash_admin_password("member-password-123"),
        credential_version=1,
        is_superadmin=False,
        enabled=True,
    )
    session: dict[str, object] = {}

    establish_browser_identity(session, user)

    assert session["portal_email"] == "member@terrasatch.com"
    assert "admin_authenticated" not in session


@pytest.mark.asyncio
async def test_legacy_admin_hash_can_promote_canonical_founder_identity() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    legacy_hash = hash_admin_password("existing-admin-password-123")

    async with factory() as session:
        account = Account(id=uuid4(), name="TerraSatch")
        organization = Organization(
            id=uuid4(),
            account_id=account.id,
            name="TerraSatch",
            slug="terrasatch",
            enabled=True,
        )
        session.add_all([account, organization])
        await session.flush()

        user, membership = await promote_superadmin_identity(
            session,
            organization_id=organization.id,
            email="keaton@terrasatch.com",
            display_name="Keaton",
            password_hash=legacy_hash,
            settings=Settings(max_portal_users=250),
        )
        await session.commit()

        assert user.email == "keaton@terrasatch.com"
        assert user.is_superadmin is True
        assert user.enabled is True
        assert verify_admin_password(
            "existing-admin-password-123",
            user.password_hash or "",
        )
        assert membership.role == MembershipRole.OWNER
        assert membership.enabled is True

    await engine.dispose()

@pytest.mark.asyncio
async def test_existing_founder_password_is_preserved_during_superadmin_promotion() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    workspace_hash = hash_admin_password("existing-workspace-password-123")
    break_glass_hash = hash_admin_password("break-glass-password-123")

    async with factory() as session:
        account = Account(id=uuid4(), name="TerraSatch")
        organization = Organization(
            id=uuid4(),
            account_id=account.id,
            name="TerraSatch",
            slug="terrasatch",
            enabled=True,
        )
        founder = User(
            id=uuid4(),
            email="keaton@terrasatch.com",
            display_name="Keaton",
            password_hash=workspace_hash,
            credential_version=1,
            enabled=True,
        )
        session.add_all([account, organization, founder])
        await session.flush()

        user, membership = await promote_superadmin_identity(
            session,
            organization_id=organization.id,
            email="keaton@terrasatch.com",
            display_name="Keaton",
            password_hash=break_glass_hash,
            settings=Settings(max_portal_users=250),
        )
        await session.commit()

        assert user.id == founder.id
        assert user.password_hash == workspace_hash
        assert user.credential_version == 1
        assert user.is_superadmin is True
        assert verify_admin_password(
            "existing-workspace-password-123",
            user.password_hash or "",
        )
        assert not verify_admin_password(
            "break-glass-password-123",
            user.password_hash or "",
        )
        assert membership.role == MembershipRole.OWNER

    await engine.dispose()

