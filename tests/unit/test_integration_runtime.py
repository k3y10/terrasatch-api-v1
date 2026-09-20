"""Capability-based Satchy integration runtime authorization tests."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.database.base import Base
from terrasatch.errors import ResourceNotFound
from terrasatch.identity.models import Account, Organization, User
from terrasatch.integrations.models import (
    IntegrationConnection,
    IntegrationGrant,
    IntegrationStatus,
)
from terrasatch.integrations.runtime import resolve_connection


@pytest.mark.asyncio
async def test_satchy_requires_audience_and_agent_capability_grants() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Runtime org",
            slug="runtime-org",
        )
        owner = User(
            email="runtime-owner@example.com",
            display_name="Runtime Owner",
            enabled=True,
        )
        other = User(
            email="runtime-other@example.com",
            display_name="Runtime Other",
            enabled=True,
        )
        session.add_all([organization, owner, other])
        await session.flush()

        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="google_drive",
            scope_type="user",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            display_name="Owner Drive",
            status=IntegrationStatus.CONNECTED.value,
            configuration={},
            enabled=True,
        )
        session.add(connection)
        await session.flush()
        audience = IntegrationGrant(
            organization_id=organization.id,
            connection_id=connection.id,
            subject_type="user",
            subject_id=str(owner.id),
            capabilities=["document.create"],
            created_by_user_id=owner.id,
            enabled=True,
        )
        agent = IntegrationGrant(
            organization_id=organization.id,
            connection_id=connection.id,
            subject_type="agent",
            subject_id="satchy",
            capabilities=["document.create"],
            created_by_user_id=owner.id,
            enabled=True,
        )
        session.add_all([audience, agent])
        await session.commit()

        resolved = await resolve_connection(
            session,
            organization_id=organization.id,
            user_id=owner.id,
            capability="document.create",
            agent_key="satchy",
        )
        assert resolved.id == connection.id

        with pytest.raises(ResourceNotFound):
            await resolve_connection(
                session,
                organization_id=organization.id,
                user_id=other.id,
                capability="document.create",
                agent_key="satchy",
            )

        agent.enabled = False
        await session.commit()
        with pytest.raises(ResourceNotFound):
            await resolve_connection(
                session,
                organization_id=organization.id,
                user_id=owner.id,
                capability="document.create",
                agent_key="satchy",
            )

        direct = await resolve_connection(
            session,
            organization_id=organization.id,
            user_id=owner.id,
            capability="document.create",
            agent_key=None,
        )
        assert direct.id == connection.id

    await engine.dispose()
