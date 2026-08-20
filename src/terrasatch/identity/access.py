"""Browser-facing human identity and organization/team membership services."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.security import hash_admin_password, verify_admin_password
from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ResourceConflict, ResourceNotFound
from terrasatch.identity.models import (
    Membership,
    MembershipRole,
    Organization,
    Team,
    TeamMembership,
    User,
)
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


@dataclass(frozen=True, slots=True)
class UserTeamAccess:
    team_membership_id: UUID
    team_id: UUID
    team_name: str
    site_id: UUID | None


def role_allows(role: MembershipRole, minimum: MembershipRole) -> bool:
    return _ROLE_RANK[role] >= _ROLE_RANK[minimum]


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User | None:
    normalized = email.strip().casefold()
    user = await session.scalar(
        select(User).where(User.email == normalized, User.enabled.is_(True))
    )
    if user is None or not user.password_hash:
        return None
    if not verify_admin_password(password, user.password_hash):
        return None
    membership_id = await session.scalar(
        select(Membership.id).where(
            Membership.user_id == user.id,
            Membership.enabled.is_(True),
        )
    )
    return user if membership_id is not None else None


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


async def list_user_team_access(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
) -> list[UserTeamAccess]:
    """Return enabled teams only after confirming organization membership."""

    await get_user_organization_access(
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    rows = await session.execute(
        select(TeamMembership, Team)
        .join(Team, Team.id == TeamMembership.team_id)
        .where(
            TeamMembership.organization_id == organization_id,
            TeamMembership.user_id == user_id,
            TeamMembership.enabled.is_(True),
            Team.organization_id == organization_id,
            Team.enabled.is_(True),
        )
        .order_by(Team.name)
    )
    return [
        UserTeamAccess(
            team_membership_id=membership.id,
            team_id=team.id,
            team_name=team.name,
            site_id=team.site_id,
        )
        for membership, team in rows.all()
    ]


async def set_user_team_memberships(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    team_ids: set[UUID],
) -> list[UserTeamAccess]:
    """Replace one user's team assignments without crossing the tenant boundary."""

    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
            Membership.enabled.is_(True),
        )
    )
    if membership is None:
        raise ResourceNotFound("User is not an enabled member of this organization")

    if team_ids:
        teams = list(
            await session.scalars(
                select(Team).where(
                    Team.organization_id == organization_id,
                    Team.id.in_(team_ids),
                    Team.enabled.is_(True),
                )
            )
        )
        missing = team_ids - {team.id for team in teams}
        if missing:
            raise InvalidConfiguration(
                "One or more teams are not enabled in the selected organization",
                details={"team_ids": sorted(str(item) for item in missing)},
            )

    existing = list(
        await session.scalars(
            select(TeamMembership).where(
                TeamMembership.organization_id == organization_id,
                TeamMembership.user_id == user_id,
            )
        )
    )
    by_team = {item.team_id: item for item in existing}
    for item in existing:
        item.enabled = item.team_id in team_ids
    for team_id in team_ids - set(by_team):
        session.add(
            TeamMembership(
                organization_id=organization_id,
                user_id=user_id,
                team_id=team_id,
                enabled=True,
            )
        )
    await session.flush()
    return await list_user_team_access(
        session,
        user_id=user_id,
        organization_id=organization_id,
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
        .where(Membership.user_id == user.id, Membership.enabled.is_(True))
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
            enabled=True,
        )
        session.add(user)
        await session.flush()
    else:
        user.display_name = normalized_name
        user.password_hash = password_hash
        user.enabled = True

    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user.id,
        )
    )
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
