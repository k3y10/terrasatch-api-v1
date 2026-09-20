"""Capability-based Satchy integration runtime authorization tests."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.identity.models import Account, Organization, Team, User
from terrasatch.integrations.models import (
    IntegrationConnection,
    IntegrationCredential,
    IntegrationDelivery,
    IntegrationGrant,
    IntegrationStatus,
)
from terrasatch.integrations.operations import ProviderQueryResult
from terrasatch.integrations.runtime import _delivery, query, resolve_connection


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



@pytest.mark.asyncio
async def test_notification_send_requires_team_and_satchy_grants() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Slack runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Slack runtime org",
            slug=f"slack-runtime-{uuid4().hex[:8]}",
        )
        requester = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Field Operator",
            enabled=True,
        )
        session.add_all([organization, requester])
        await session.flush()
        team = Team(
            organization_id=organization.id,
            name="Field Team",
            enabled=True,
        )
        session.add(team)
        await session.flush()

        slack = IntegrationConnection(
            organization_id=organization.id,
            provider="slack",
            scope_type="team",
            team_id=team.id,
            created_by_user_id=requester.id,
            display_name="Field Team Slack",
            status=IntegrationStatus.CONNECTED.value,
            configuration={},
            enabled=True,
        )
        session.add(slack)
        await session.flush()
        session.add_all(
            [
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=slack.id,
                    subject_type="team",
                    subject_id=str(team.id),
                    capabilities=["notification.send"],
                    created_by_user_id=requester.id,
                    enabled=True,
                ),
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=slack.id,
                    subject_type="agent",
                    subject_id="satchy",
                    capabilities=["notification.send"],
                    created_by_user_id=requester.id,
                    enabled=True,
                ),
            ]
        )
        await session.commit()

        with pytest.raises(ResourceNotFound):
            await resolve_connection(
                session,
                organization_id=organization.id,
                user_id=requester.id,
                capability="notification.send",
                agent_key="satchy",
            )

        resolved = await resolve_connection(
            session,
            organization_id=organization.id,
            user_id=None,
            team_ids=(team.id,),
            capability="notification.send",
            agent_key="satchy",
        )
        assert resolved.id == slack.id

    await engine.dispose()



@pytest.mark.asyncio
async def test_arcgis_query_runtime_enforces_connection_layer_allowlist(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    approved_layer = (
        "https://services3.arcgis.com/ORG/arcgis/rest/services/"
        "Avalanche_Observations/FeatureServer/0"
    )
    other_layer = (
        "https://services3.arcgis.com/ORG/arcgis/rest/services/"
        "Other_Layer/FeatureServer/0"
    )

    async with factory() as session:
        account = Account(name="ArcGIS runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="ArcGIS runtime org",
            slug=f"arcgis-runtime-{uuid4().hex[:8]}",
        )
        owner = User(
            email=f"{uuid4().hex}@example.com",
            display_name="GIS User",
            enabled=True,
        )
        session.add_all([organization, owner])
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="esri_arcgis",
            scope_type="user",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            display_name="GIS Layers",
            status=IntegrationStatus.CONNECTED.value,
            configuration={"feature_layer_urls": [approved_layer]},
            enabled=True,
        )
        session.add(connection)
        await session.flush()
        session.add_all(
            [
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="user",
                    subject_id=str(owner.id),
                    capabilities=["map.features.query"],
                    created_by_user_id=owner.id,
                    enabled=True,
                ),
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="agent",
                    subject_id="satchy",
                    capabilities=["map.features.query"],
                    created_by_user_id=owner.id,
                    enabled=True,
                ),
            ]
        )
        await session.commit()

        async def fake_credentials(*args, **kwargs):
            return {"access_token": "arcgis-access"}, object()

        async def fake_query(*args, **kwargs):
            return ProviderQueryResult(
                data={"features": []},
                metadata={"feature_count": 0},
            )

        monkeypatch.setattr(
            "terrasatch.integrations.runtime.active_credentials",
            fake_credentials,
        )
        monkeypatch.setattr(
            "terrasatch.integrations.runtime.query_arcgis_features",
            fake_query,
        )

        result = await query(
            session,
            Settings(),
            organization_id=organization.id,
            user_id=owner.id,
            capability="map.features.query",
            payload={"layer_url": approved_layer},
            agent_key="satchy",
        )
        assert result["metadata"]["feature_count"] == 0

        with pytest.raises(InvalidConfiguration, match="not approved"):
            await query(
                session,
                Settings(),
                organization_id=organization.id,
                user_id=owner.id,
                capability="map.features.query",
                payload={"layer_url": other_layer},
                agent_key="satchy",
            )

    await engine.dispose()



@pytest.mark.asyncio
async def test_delivery_duplicate_does_not_rollback_unrelated_state() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Idempotency account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Idempotency org",
            slug=f"idempotency-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Idempotency User",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="google_drive",
            scope_type="user",
            owner_user_id=user.id,
            created_by_user_id=user.id,
            display_name="Drive",
            status=IntegrationStatus.CONNECTED.value,
            configuration={},
            enabled=True,
        )
        session.add(connection)
        await session.flush()

        request_id = uuid4()
        existing = IntegrationDelivery(
            organization_id=organization.id,
            connection_id=connection.id,
            requested_by_user_id=user.id,
            request_id=request_id,
            operation="document.create",
            status="pending",
            request_metadata={},
            response_metadata={},
        )
        session.add(existing)
        await session.commit()

        organization.name = "Idempotency org updated"
        delivery, created = await _delivery(
            session,
            organization_id=organization.id,
            connection=connection,
            user_id=user.id,
            request_id=request_id,
            capability="document.create",
            request_metadata={"content_bytes": 1},
        )
        assert created is False
        assert delivery.id == existing.id
        assert organization.name == "Idempotency org updated"
        assert session.dirty

    await engine.dispose()
