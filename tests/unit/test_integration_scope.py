"""Authorization boundaries for personal, team, and organization integrations."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.database.base import Base
from terrasatch.errors import ResourceNotFound
from terrasatch.identity.models import (
    Account,
    Membership,
    MembershipRole,
    Organization,
    Team,
    User,
)
from terrasatch.integrations.models import IntegrationConnection, IntegrationScope
from terrasatch.integrations.service import (
    get_connection_for_management,
    list_visible_connections,
)


@pytest.mark.asyncio
async def test_personal_connection_remains_private_even_from_org_admin() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Integration account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Integration org",
            slug="integration-org",
        )
        session.add(organization)
        owner = User(
            email="owner@example.com",
            display_name="Owner",
            enabled=True,
        )
        admin = User(
            email="admin@example.com",
            display_name="Admin",
            enabled=True,
        )
        session.add_all([owner, admin])
        await session.flush()
        session.add_all(
            [
                Membership(
                    organization_id=organization.id,
                    user_id=owner.id,
                    role=MembershipRole.OPERATOR,
                    enabled=True,
                ),
                Membership(
                    organization_id=organization.id,
                    user_id=admin.id,
                    role=MembershipRole.ADMIN,
                    enabled=True,
                ),
            ]
        )
        personal = IntegrationConnection(
            organization_id=organization.id,
            provider="google_drive",
            scope_type=IntegrationScope.USER.value,
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            display_name="Owner Drive",
            status="connected",
            configuration={},
            enabled=True,
        )
        session.add(personal)
        await session.commit()

        with pytest.raises(ResourceNotFound):
            await get_connection_for_management(
                session,
                organization_id=organization.id,
                user_id=admin.id,
                role=MembershipRole.ADMIN,
                connection_id=personal.id,
            )

        admin_visible = await list_visible_connections(
            session,
            organization_id=organization.id,
            user_id=admin.id,
            role=MembershipRole.ADMIN,
        )
        assert personal.id not in {item.id for item in admin_visible}

    await engine.dispose()


@pytest.mark.asyncio
async def test_team_metadata_is_admin_only_until_portal_team_membership_exists() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Scoped account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Scoped org",
            slug="scoped-org",
        )
        session.add(organization)
        operator = User(
            email="operator@example.com",
            display_name="Operator",
            enabled=True,
        )
        admin = User(
            email="admin2@example.com",
            display_name="Admin",
            enabled=True,
        )
        session.add_all([operator, admin])
        await session.flush()
        session.add_all(
            [
                Membership(
                    organization_id=organization.id,
                    user_id=operator.id,
                    role=MembershipRole.OPERATOR,
                    enabled=True,
                ),
                Membership(
                    organization_id=organization.id,
                    user_id=admin.id,
                    role=MembershipRole.ADMIN,
                    enabled=True,
                ),
            ]
        )
        team = Team(
            organization_id=organization.id,
            name="Field Team",
            enabled=True,
        )
        session.add(team)
        await session.flush()
        team_connection = IntegrationConnection(
            organization_id=organization.id,
            provider="slack",
            scope_type=IntegrationScope.TEAM.value,
            team_id=team.id,
            created_by_user_id=admin.id,
            display_name="Field Team Slack",
            status="connected",
            configuration={},
            enabled=True,
        )
        org_connection = IntegrationConnection(
            organization_id=organization.id,
            provider="snowflake",
            scope_type=IntegrationScope.ORGANIZATION.value,
            created_by_user_id=admin.id,
            display_name="Org warehouse",
            status="requested",
            configuration={},
            enabled=True,
        )
        session.add_all([team_connection, org_connection])
        await session.commit()

        operator_visible = await list_visible_connections(
            session,
            organization_id=organization.id,
            user_id=operator.id,
            role=MembershipRole.OPERATOR,
        )
        assert {item.id for item in operator_visible} == {org_connection.id}

        admin_visible = await list_visible_connections(
            session,
            organization_id=organization.id,
            user_id=admin.id,
            role=MembershipRole.ADMIN,
        )
        assert {item.id for item in admin_visible} == {
            team_connection.id,
            org_connection.id,
        }

    await engine.dispose()
