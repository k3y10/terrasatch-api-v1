"""Capability-based Satchy integration runtime authorization tests."""

from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.identity.models import Account, MembershipRole, Organization, Team, User
from terrasatch.integrations.models import (
    IntegrationConnection,
    IntegrationDelivery,
    IntegrationGrant,
    IntegrationScope,
    IntegrationStatus,
)
from terrasatch.integrations.operations import ProviderOperationResult, ProviderQueryResult
from terrasatch.integrations.runtime import _delivery, execute, query, resolve_connection
from terrasatch.integrations.service import create_connection_request


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
        organization_id = organization.id
        await session.commit()

    async with factory() as verification:
        persisted = await verification.get(Organization, organization_id)
        assert persisted is not None
        assert persisted.name == "Idempotency org updated"

    await engine.dispose()



@pytest.mark.asyncio
async def test_microsoft_document_create_uses_generic_runtime(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Microsoft runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Microsoft runtime org",
            slug=f"microsoft-runtime-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Microsoft User",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="microsoft_365",
            scope_type="user",
            owner_user_id=user.id,
            created_by_user_id=user.id,
            display_name="My OneDrive",
            status=IntegrationStatus.CONNECTED.value,
            configuration={"folder_path": "Reports"},
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
                    subject_id=str(user.id),
                    capabilities=["document.create"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="agent",
                    subject_id="satchy",
                    capabilities=["document.create"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
            ]
        )
        await session.commit()

        async def fake_credentials(*args, **kwargs):
            return {"access_token": "ms-access"}, object()

        async def fake_create(*args, **kwargs):
            assert kwargs["folder_path"] == "Reports"
            assert kwargs["name"] == "handoff.md"
            return ProviderOperationResult(
                external_id="drive-item-1",
                metadata={"name": "handoff.md"},
            )

        monkeypatch.setattr(
            "terrasatch.integrations.runtime.active_credentials",
            fake_credentials,
        )
        monkeypatch.setattr(
            "terrasatch.integrations.runtime.create_microsoft_drive_file",
            fake_create,
        )

        delivery = await execute(
            session,
            Settings(),
            organization_id=organization.id,
            user_id=user.id,
            capability="document.create",
            request_id=uuid4(),
            payload={
                "name": "handoff.md",
                "content": "Shift handoff",
                "mime_type": "text/markdown",
            },
        )
        assert delivery.status == "delivered"
        assert delivery.external_id == "drive-item-1"

    await engine.dispose()


@pytest.mark.asyncio
async def test_snowflake_data_query_routes_through_org_grants(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Snowflake runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Snowflake runtime org",
            slug=f"snowflake-runtime-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Data User",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="snowflake",
            scope_type="organization",
            created_by_user_id=user.id,
            display_name="Read-only warehouse",
            status=IntegrationStatus.CONNECTED.value,
            configuration={
                "account_host": "org-account.snowflakecomputing.com",
            },
            enabled=True,
        )
        session.add(connection)
        await session.flush()
        session.add_all(
            [
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="organization",
                    subject_id=str(organization.id),
                    capabilities=["data.query"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="agent",
                    subject_id="satchy",
                    capabilities=["data.query"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
            ]
        )
        await session.commit()

        async def fake_credentials(*args, **kwargs):
            return {"programmatic_access_token": "snow-pat"}, object()

        async def fake_query(*args, **kwargs):
            assert kwargs["statement"] == "SELECT CURRENT_TIMESTAMP()"
            return ProviderQueryResult(
                data={"data": [["2026-09-20"]]},
                metadata={"row_count": 1},
            )

        monkeypatch.setattr(
            "terrasatch.integrations.runtime.active_credentials",
            fake_credentials,
        )
        monkeypatch.setattr(
            "terrasatch.integrations.runtime.query_snowflake",
            fake_query,
        )

        result = await query(
            session,
            Settings(),
            organization_id=organization.id,
            user_id=user.id,
            capability="data.query",
            payload={"statement": "SELECT CURRENT_TIMESTAMP()"},
        )
        assert result["provider"] == "snowflake"
        assert result["metadata"]["row_count"] == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_caltopo_map_query_requires_team_grant_and_allowlisted_map(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="CalTopo runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="CalTopo runtime org",
            slug=f"caltopo-runtime-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Map User",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        team = Team(
            organization_id=organization.id,
            name="Field Team",
            enabled=True,
        )
        session.add(team)
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="caltopo",
            scope_type="team",
            team_id=team.id,
            created_by_user_id=user.id,
            display_name="Field maps",
            status=IntegrationStatus.CONNECTED.value,
            configuration={
                "caltopo_team_id": "ABC123",
                "map_ids": ["MAP123"],
            },
            enabled=True,
        )
        session.add(connection)
        await session.flush()
        session.add_all(
            [
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="team",
                    subject_id=str(team.id),
                    capabilities=["map.features.query"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="agent",
                    subject_id="satchy",
                    capabilities=["map.features.query"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
            ]
        )
        await session.commit()

        async def fake_credentials(*args, **kwargs):
            return {
                "credential_id": "credential-id",
                "credential_secret": "secret",
            }, object()

        async def fake_map_query(*args, **kwargs):
            assert kwargs["map_id"] == "MAP123"
            return ProviderQueryResult(
                data={"features": []},
                metadata={"feature_count": 0},
            )

        monkeypatch.setattr(
            "terrasatch.integrations.runtime.active_credentials",
            fake_credentials,
        )
        monkeypatch.setattr(
            "terrasatch.integrations.runtime.query_caltopo_map",
            fake_map_query,
        )

        result = await query(
            session,
            Settings(),
            organization_id=organization.id,
            user_id=None,
            team_ids=(team.id,),
            capability="map.features.query",
            payload={"map_id": "MAP123"},
        )
        assert result["provider"] == "caltopo"

        with pytest.raises(InvalidConfiguration, match="not approved"):
            await query(
                session,
                Settings(),
                organization_id=organization.id,
                user_id=None,
                team_ids=(team.id,),
                capability="map.features.query",
                payload={"map_id": "OTHER1"},
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_mapbox_managed_runtime_enforces_style_allowlist(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        integration_provider_config_json=SecretStr(
            '{"mapbox":{"access_token":"pk.test","username":"terrasatch",'
            '"style_ids":"field-style,incident-style"}}'
        )
    )

    async def fake_style(*args, **kwargs):
        assert kwargs["access_token"] == "pk.test"
        assert kwargs["username"] == "terrasatch"
        assert kwargs["style_id"] == "field-style"
        return ProviderQueryResult(
            data={"version": 8, "name": "Field"},
            metadata={"name": "Field"},
        )

    monkeypatch.setattr(
        "terrasatch.integrations.runtime.read_mapbox_style",
        fake_style,
    )

    async with factory() as session:
        result = await query(
            session,
            settings,
            organization_id=uuid4(),
            user_id=uuid4(),
            capability="map.style.read",
            payload={"style_id": "field-style"},
        )
        assert result["provider"] == "mapbox"

        with pytest.raises(InvalidConfiguration, match="not approved"):
            await query(
                session,
                settings,
                organization_id=uuid4(),
                user_id=uuid4(),
                capability="map.style.read",
                payload={"style_id": "private-style"},
            )

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "operation_name"),
    [
        ("microsoft_teams", "send_teams_message"),
        ("webhook", "send_webhook_notification"),
    ],
)
async def test_notification_runtime_routes_manual_webhook_providers(
    monkeypatch,
    provider: str,
    operation_name: str,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name=f"{provider} runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name=f"{provider} runtime org",
            slug=f"{provider.replace('_', '-')}-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Notification User",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider=provider,
            scope_type="organization",
            created_by_user_id=user.id,
            display_name=provider,
            status=IntegrationStatus.CONNECTED.value,
            configuration={},
            enabled=True,
        )
        session.add(connection)
        await session.flush()
        session.add_all(
            [
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="organization",
                    subject_id=str(organization.id),
                    capabilities=["notification.send"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="agent",
                    subject_id="satchy",
                    capabilities=["notification.send"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
            ]
        )
        await session.commit()

        async def fake_credentials(*args, **kwargs):
            return {"webhook_url": "https://example.com/hook"}, object()

        async def fake_send(*args, **kwargs):
            assert kwargs["text"] == "Field update"
            if provider == "webhook":
                assert "request_id" in kwargs
            return ProviderOperationResult(
                external_id=f"{provider}-1",
                metadata={"status_code": 202},
            )

        monkeypatch.setattr(
            "terrasatch.integrations.runtime.active_credentials",
            fake_credentials,
        )
        monkeypatch.setattr(
            f"terrasatch.integrations.runtime.{operation_name}",
            fake_send,
        )

        delivery = await execute(
            session,
            Settings(),
            organization_id=organization.id,
            user_id=user.id,
            capability="notification.send",
            request_id=uuid4(),
            payload={"text": "Field update"},
        )
        assert delivery.status == "delivered"
        assert delivery.external_id == f"{provider}-1"

    await engine.dispose()


@pytest.mark.asyncio
async def test_r2_document_create_uses_generic_runtime(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="R2 runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="R2 runtime org",
            slug=f"r2-runtime-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="R2 User",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="cloudflare_r2",
            scope_type="organization",
            created_by_user_id=user.id,
            display_name="R2 reports",
            status=IntegrationStatus.CONNECTED.value,
            configuration={
                "endpoint_url": "https://abc123.r2.cloudflarestorage.com",
                "bucket": "field-reports",
                "prefix": "exports",
            },
            enabled=True,
        )
        session.add(connection)
        await session.flush()
        session.add_all(
            [
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="organization",
                    subject_id=str(organization.id),
                    capabilities=["document.create"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="agent",
                    subject_id="satchy",
                    capabilities=["document.create"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
            ]
        )
        await session.commit()

        async def fake_credentials(*args, **kwargs):
            return {
                "access_key_id": "r2-access",
                "secret_access_key": "r2-secret",
            }, object()

        async def fake_put(*args, **kwargs):
            assert kwargs["endpoint_url"] == "https://abc123.r2.cloudflarestorage.com"
            assert kwargs["bucket"] == "field-reports"
            assert kwargs["prefix"] == "exports"
            assert kwargs["name"] == "handoff.md"
            assert kwargs["content"] == "Shift handoff"
            return ProviderOperationResult(
                external_id="exports/handoff.md",
                metadata={"bucket": "field-reports"},
            )

        monkeypatch.setattr(
            "terrasatch.integrations.runtime.active_credentials",
            fake_credentials,
        )
        monkeypatch.setattr(
            "terrasatch.integrations.runtime.put_cloudflare_r2_object",
            fake_put,
        )

        delivery = await execute(
            session,
            Settings(),
            organization_id=organization.id,
            user_id=user.id,
            capability="document.create",
            request_id=uuid4(),
            payload={
                "name": "handoff.md",
                "content": "Shift handoff",
                "mime_type": "text/markdown",
            },
        )
        assert delivery.status == "delivered"
        assert delivery.external_id == "exports/handoff.md"

    await engine.dispose()


@pytest.mark.asyncio
async def test_aws_s3_document_create_uses_generic_runtime(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="AWS S3 runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="AWS S3 runtime org",
            slug=f"aws-s3-runtime-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="AWS S3 User",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="aws_s3",
            scope_type="organization",
            created_by_user_id=user.id,
            display_name="AWS reports",
            status=IntegrationStatus.CONNECTED.value,
            configuration={
                "region": "us-west-2",
                "bucket": "field-reports",
                "prefix": "exports",
            },
            enabled=True,
        )
        session.add(connection)
        await session.flush()
        session.add_all(
            [
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="organization",
                    subject_id=str(organization.id),
                    capabilities=["document.create"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
                IntegrationGrant(
                    organization_id=organization.id,
                    connection_id=connection.id,
                    subject_type="agent",
                    subject_id="satchy",
                    capabilities=["document.create"],
                    created_by_user_id=user.id,
                    enabled=True,
                ),
            ]
        )
        await session.commit()

        async def fake_credentials(*args, **kwargs):
            return {
                "access_key_id": "aws-access",
                "secret_access_key": "aws-secret",
            }, object()

        async def fake_put(*args, **kwargs):
            assert kwargs["region"] == "us-west-2"
            assert kwargs["bucket"] == "field-reports"
            assert kwargs["prefix"] == "exports"
            assert kwargs["name"] == "handoff.md"
            assert kwargs["content"] == "Shift handoff"
            return ProviderOperationResult(
                external_id="exports/handoff.md",
                metadata={"bucket": "field-reports", "region": "us-west-2"},
            )

        monkeypatch.setattr(
            "terrasatch.integrations.runtime.active_credentials",
            fake_credentials,
        )
        monkeypatch.setattr(
            "terrasatch.integrations.runtime.put_aws_s3_object",
            fake_put,
        )

        delivery = await execute(
            session,
            Settings(),
            organization_id=organization.id,
            user_id=user.id,
            capability="document.create",
            request_id=uuid4(),
            payload={
                "name": "handoff.md",
                "content": "Shift handoff",
                "mime_type": "text/markdown",
            },
        )
        assert delivery.status == "delivered"
        assert delivery.external_id == "exports/handoff.md"

    await engine.dispose()


@pytest.mark.asyncio
async def test_operational_email_connection_and_runtime_use_platform_resend(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        resend_api_key=SecretStr("re_test_ops"),
        integration_email_from=(
            "TerraSatch Operations <operations@terrasatch.com>"
        ),
        integration_email_reply_to="support@terrasatch.com",
    )

    async with factory() as session:
        account = Account(name="Email runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Email runtime org",
            slug=f"email-runtime-{uuid4().hex[:8]}",
        )
        admin = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Email Admin",
            enabled=True,
        )
        session.add_all([organization, admin])
        await session.flush()

        connection = await create_connection_request(
            session,
            settings=settings,
            organization_id=organization.id,
            user_id=admin.id,
            role=MembershipRole.ADMIN,
            provider_key="email",
            scope=IntegrationScope.ORGANIZATION,
            team_id=None,
            display_name="Field operations email",
            configuration={
                "recipients": ["OPS@example.com", "lead@example.com"],
                "subject": "Field operations update",
            },
        )
        await session.commit()

        assert connection.status == IntegrationStatus.CONNECTED.value
        assert connection.provider_account_label == "TerraSatch Resend"
        assert connection.configuration["recipients"] == [
            "ops@example.com",
            "lead@example.com",
        ]

        async def unexpected_credentials(*args, **kwargs):
            raise AssertionError("platform email must not load customer credentials")

        async def fake_email(**kwargs):
            assert kwargs["api_key"] == "re_test_ops"
            assert kwargs["sender"] == (
                "TerraSatch Operations <operations@terrasatch.com>"
            )
            assert kwargs["recipients"] == [
                "ops@example.com",
                "lead@example.com",
            ]
            assert kwargs["subject"] == "Field operations update"
            assert kwargs["text"] == "Field update"
            assert kwargs["connection_id"] == connection.id
            assert kwargs["reply_to"] == "support@terrasatch.com"
            return ProviderOperationResult(
                external_id="email_ops_123",
                metadata={"provider": "resend", "recipient_count": 2},
            )

        monkeypatch.setattr(
            "terrasatch.integrations.runtime.active_credentials",
            unexpected_credentials,
        )
        monkeypatch.setattr(
            "terrasatch.integrations.runtime.send_resend_notification",
            fake_email,
        )

        delivery = await execute(
            session,
            settings,
            organization_id=organization.id,
            user_id=admin.id,
            capability="notification.send",
            request_id=uuid4(),
            payload={"text": "Field update"},
        )
        assert delivery.status == "delivered"
        assert delivery.external_id == "email_ops_123"
        assert delivery.response_metadata == {
            "provider": "resend",
            "recipient_count": 2,
        }

    await engine.dispose()


@pytest.mark.asyncio
async def test_geojson_runtime_uses_fixed_public_endpoint_without_credentials(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="GeoJSON runtime account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="GeoJSON runtime org",
            slug=f"geojson-runtime-{uuid4().hex[:8]}",
        )
        admin = User(
            email=f"{uuid4().hex}@example.com",
            display_name="GeoJSON Admin",
            enabled=True,
        )
        session.add_all([organization, admin])
        await session.flush()

        async def fake_public_destination(value):
            assert value == "https://data.example.com/observations.geojson"
            return value

        monkeypatch.setattr(
            "terrasatch.integrations.service.validate_public_geojson_destination",
            fake_public_destination,
        )

        connection = await create_connection_request(
            session,
            organization_id=organization.id,
            user_id=admin.id,
            role=MembershipRole.ADMIN,
            provider_key="geojson",
            scope=IntegrationScope.ORGANIZATION,
            team_id=None,
            display_name="Field observations",
            configuration={
                "endpoint_url": "https://data.example.com/observations.geojson",
                "max_features": 250,
            },
        )
        await session.commit()

        assert connection.status == IntegrationStatus.CONNECTED.value
        assert connection.provider_account_id == "data.example.com"

        async def unexpected_credentials(*args, **kwargs):
            raise AssertionError("public GeoJSON must not load customer credentials")

        async def fake_query(**kwargs):
            assert kwargs == {
                "endpoint_url": "https://data.example.com/observations.geojson",
                "max_features": 250,
            }
            return ProviderQueryResult(
                data={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": None,
                            "properties": {"name": "Observation"},
                        }
                    ],
                },
                metadata={
                    "source_host": "data.example.com",
                    "feature_count": 1,
                    "source_feature_count": 1,
                    "truncated": False,
                },
            )

        monkeypatch.setattr(
            "terrasatch.integrations.runtime.active_credentials",
            unexpected_credentials,
        )
        monkeypatch.setattr(
            "terrasatch.integrations.runtime.query_geojson_features",
            fake_query,
        )

        result = await query(
            session,
            Settings(),
            organization_id=organization.id,
            user_id=admin.id,
            capability="map.features.query",
            payload={},
            connection_id=connection.id,
        )
        assert result["provider"] == "geojson"
        assert result["metadata"]["feature_count"] == 1

        with pytest.raises(InvalidConfiguration, match="does not accept runtime"):
            await query(
                session,
                Settings(),
                organization_id=organization.id,
                user_id=admin.id,
                capability="map.features.query",
                payload={"endpoint_url": "https://other.example.com/feed.geojson"},
                connection_id=connection.id,
            )

    await engine.dispose()
