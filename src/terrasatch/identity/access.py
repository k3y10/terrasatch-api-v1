"""Browser-facing human identity and organization membership services."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.security import hash_admin_password, verify_admin_password
from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ResourceConflict, ResourceNotFound
from terrasatch.identity.models import Membership, MembershipRole, Organization, User
from terrasatch.network.status import count_portal_users

_ROLE_RANK = {
    MembershipRole.VIEWER: 10,
    MembershipRole.OPERATOR: 20,
    MembershipRole.ADMIN: 30,
    MembershipRole.OWNER: 40,
}


@dataclass(frozen=True, slots=True)
class UserOrganizationAccess:
    membership_id: UUID
    organization_id: UUID
    organization_name: str
    organization_slug: str
    role: MembershipRole


def role_allows(role: MembershipRole, minimum: MembershipRole) -> bool:
    return _ROLE_RANK[role] >= _ROLE_RANK[minimum]


def establish_browser_identity(
    browser_session: MutableMapping[str, Any],
    user: User,
) -> None:
    """Create one shared browser identity for portal and platform administration."""

    browser_session.clear()
    browser_session["portal_user_id"] = str(user.id)
    browser_session["portal_credential_version"] = user.credential_version
    browser_session["portal_email"] = user.email
    browser_session["portal_display_name"] = user.display_name
    if user.is_superadmin:
        browser_session["admin_authenticated"] = True


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User | None:
    normalized = email.strip().casefold()
    user = await session.scalar(
        select(User).where(
            User.email == normalized,
            User.enabled.is_(True),
        )
    )
    if user is None or not user.password_hash:
        return None
    if not verify_admin_password(password, user.password_hash):
        return None
    memberships = await session.scalar(
        select(Membership.id).where(
            Membership.user_id == user.id,
            Membership.enabled.is_(True),
        )
    )
    return user if memberships is not None else None


async def validate_browser_session(
    session: AsyncSession,
    *,
    user_id: UUID,
    credential_version: int,
) -> User | None:
    """Return the user only when the signed browser session matches current credentials."""

    user = await session.scalar(
        select(User).where(User.id == user_id, User.enabled.is_(True))
    )
    if user is None or user.credential_version != credential_version:
        return None
    return user


async def list_user_access(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> list[UserOrganizationAccess]:
    rows = await session.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == user_id,
            Membership.enabled.is_(True),
            Organization.enabled.is_(True),
        )
        .order_by(Organization.name)
    )
    return [
        UserOrganizationAccess(
            membership_id=membership.id,
            organization_id=organization.id,
            organization_name=organization.name,
            organization_slug=organization.slug,
            role=membership.role,
        )
        for membership, organization in rows.all()
    ]


async def get_user_organization_access(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
) -> UserOrganizationAccess:
    row = (
        await session.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(
                Membership.user_id == user_id,
                Membership.organization_id == organization_id,
                Membership.enabled.is_(True),
                Organization.enabled.is_(True),
            )
        )
    ).first()
    if row is None:
        raise ResourceNotFound("Organization access was not found for this user")
    membership, organization = row
    return UserOrganizationAccess(
        membership_id=membership.id,
        organization_id=organization.id,
        organization_name=organization.name,
        organization_slug=organization.slug,
        role=membership.role,
    )


async def list_organization_members(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> list[tuple[Membership, User]]:
    rows = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id)
        .order_by(User.display_name, User.email)
    )
    return list(rows.all())


async def _user_counts_toward_capacity(session: AsyncSession, user: User) -> bool:
    if not user.enabled:
        return False
    membership_id = await session.scalar(
        select(Membership.id)
        .where(
            Membership.user_id == user.id,
            Membership.enabled.is_(True),
        )
        .limit(1)
    )
    return membership_id is not None


async def create_or_update_organization_member(
    session: AsyncSession,
    *,
    organization_id: UUID,
    email: str,
    display_name: str,
    password: str,
    role: MembershipRole,
    settings: Settings | None = None,
) -> tuple[User, Membership]:
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise ResourceNotFound("Organization was not found")

    normalized_email = email.strip().casefold()
    normalized_name = display_name.strip()
    if not normalized_email or "@" not in normalized_email:
        raise InvalidConfiguration("A valid member email is required")
    if not normalized_name:
        raise InvalidConfiguration("Member display name is required")

    try:
        password_hash = hash_admin_password(password)
    except ValueError as error:
        raise InvalidConfiguration(str(error)) from error

    user = await session.scalar(select(User).where(User.email == normalized_email))
    membership = None
    if user is not None:
        membership = await session.scalar(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user.id,
            )
        )

    if membership is None or not membership.enabled:
        from terrasatch.billing.entitlements import enforce_member_slot

        await enforce_member_slot(session, organization_id=organization_id)

    already_counted = user is not None and await _user_counts_toward_capacity(session, user)
    if not already_counted and settings is not None:
        registered_users = await count_portal_users(session)
        if registered_users >= settings.max_portal_users:
            raise ResourceConflict(
                "Member registration is temporarily paused because the configured "
                "network capacity was reached.",
                details={
                    "registered_members": registered_users,
                    "max_portal_users": settings.max_portal_users,
                },
            )

    if user is None:
        user = User(
            email=normalized_email,
            display_name=normalized_name,
            password_hash=password_hash,
            credential_version=1,
            enabled=True,
        )
        session.add(user)
        await session.flush()
    else:
        user.display_name = normalized_name
        user.password_hash = password_hash
        user.credential_version += 1
        user.enabled = True

    if membership is None:
        membership = Membership(
            organization_id=organization_id,
            user_id=user.id,
            role=role,
            enabled=True,
        )
        session.add(membership)
    else:
        membership.role = role
        membership.enabled = True

    await session.flush()
    return user, membership


async def migrate_legacy_admin_identity(
    session: AsyncSession,
    *,
    organization_id: UUID,
    email: str,
    display_name: str,
    legacy_password_hash: str,
    settings: Settings | None = None,
) -> tuple[User, Membership]:
    """Promote one database-backed identity using the legacy admin password hash.

    This is a one-way compatibility bridge for deployments moving from the
    environment-backed superadmin credential to the normal User identity.
    """

    organization = await session.get(Organization, organization_id)
    if organization is None or not organization.enabled:
        raise ResourceNotFound("Organization was not found")

    normalized_email = email.strip().casefold()
    normalized_name = display_name.strip()
    if not normalized_email or "@" not in normalized_email:
        raise InvalidConfiguration("A valid superadmin email is required")
    if not normalized_name:
        raise InvalidConfiguration("Superadmin display name is required")
    try:
        algorithm, n_value, r_value, p_value, _salt, _digest = legacy_password_hash.split("$")
        valid_hash = algorithm == "scrypt" and (
            int(n_value),
            int(r_value),
            int(p_value),
        ) == (16_384, 8, 1)
    except (TypeError, ValueError):
        valid_hash = False
    if not valid_hash:
        raise InvalidConfiguration("Legacy admin password hash is invalid")

    user = await session.scalar(select(User).where(User.email == normalized_email))
    membership = None
    if user is not None:
        membership = await session.scalar(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user.id,
            )
        )

    if membership is None or not membership.enabled:
        from terrasatch.billing.entitlements import enforce_member_slot

        await enforce_member_slot(session, organization_id=organization_id)

    already_counted = user is not None and await _user_counts_toward_capacity(session, user)
    if not already_counted and settings is not None:
        registered_users = await count_portal_users(session)
        if registered_users >= settings.max_portal_users:
            raise ResourceConflict(
                "Member registration is temporarily paused because the configured "
                "network capacity was reached.",
                details={
                    "registered_members": registered_users,
                    "max_portal_users": settings.max_portal_users,
                },
            )

    if user is None:
        user = User(
            email=normalized_email,
            display_name=normalized_name,
            password_hash=legacy_password_hash,
            credential_version=1,
            is_superadmin=True,
            enabled=True,
        )
        session.add(user)
        await session.flush()
    else:
        user.display_name = normalized_name
        user.password_hash = legacy_password_hash
        user.credential_version += 1
        user.is_superadmin = True
        user.enabled = True

    if membership is None:
        membership = Membership(
            organization_id=organization_id,
            user_id=user.id,
            role=MembershipRole.OWNER,
            enabled=True,
        )
        session.add(membership)
    else:
        membership.role = MembershipRole.OWNER
        membership.enabled = True

    await session.flush()
    return user, membership
