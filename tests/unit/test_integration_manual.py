"""Encrypted manual integration credential lifecycle tests."""

from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import Account, MembershipRole, Organization, User
from terrasatch.integrations.crypto import decrypt_payload
from terrasatch.integrations.manual_service import bind_manual_credentials
from terrasatch.integrations.models import (
    IntegrationConnection,
    IntegrationCredential,
    IntegrationStatus,
)


@pytest.mark.asyncio
async def test_snowflake_manual_secret_is_encrypted_and_connection_is_safe(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        integration_encryption_key=SecretStr(
            Fernet.generate_key().decode("ascii")
        )
    )

    async with factory() as session:
        account = Account(name="Manual integration account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Manual integration org",
            slug=f"manual-integration-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Integration Admin",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()

        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="snowflake",
            scope_type="organization",
            created_by_user_id=user.id,
            display_name="Read-only Snowflake",
            status=IntegrationStatus.REQUESTED.value,
            configuration={
                "account_host": "org-account.snowflakecomputing.com",
            },
            enabled=True,
        )
        session.add(connection)
        await session.flush()

        async def fake_probe(provider, credentials, configuration):
            assert provider == "snowflake"
            assert credentials == {
                "programmatic_access_token": "super-secret-pat",
            }
            assert configuration["account_host"] == (
                "org-account.snowflakecomputing.com"
            )
            return "org-account.snowflakecomputing.com", (
                "org-account.snowflakecomputing.com"
            )

        monkeypatch.setattr(
            "terrasatch.integrations.manual_service.probe_manual_credentials",
            fake_probe,
        )
        connected = await bind_manual_credentials(
            session,
            settings,
            organization_id=organization.id,
            user_id=user.id,
            role=MembershipRole.ADMIN,
            connection_id=connection.id,
            values={"programmatic_access_token": "super-secret-pat"},
        )
        await session.commit()

        credential = await session.scalar(
            select(IntegrationCredential).where(
                IntegrationCredential.connection_id == connection.id
            )
        )
        assert credential is not None
        assert "super-secret-pat" not in credential.encrypted_payload
        assert decrypt_payload(settings, credential.encrypted_payload) == {
            "programmatic_access_token": "super-secret-pat",
        }
        assert connected.status == IntegrationStatus.CONNECTED.value
        assert connected.credential_ref == f"database:{credential.id}"
        assert "super-secret-pat" not in str(connected.configuration)

    await engine.dispose()


@pytest.mark.asyncio
async def test_webhook_secret_url_and_signing_secret_are_encrypted(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii"))
    )

    async with factory() as session:
        account = Account(name="Webhook integration account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Webhook integration org",
            slug=f"webhook-integration-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Webhook Admin",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="webhook",
            scope_type="organization",
            created_by_user_id=user.id,
            display_name="Dispatch webhook",
            status=IntegrationStatus.REQUESTED.value,
            configuration={},
            enabled=True,
        )
        session.add(connection)
        await session.flush()

        async def fake_probe(provider, credentials, configuration):
            assert provider == "webhook"
            assert configuration == {}
            assert credentials["webhook_url"].startswith("https://ops.example.com/")
            assert credentials["signing_secret"] == "shared-secret"
            return "Webhook · ops.example.com", "ops.example.com"

        monkeypatch.setattr(
            "terrasatch.integrations.manual_service.probe_manual_credentials",
            fake_probe,
        )
        connected = await bind_manual_credentials(
            session,
            settings,
            organization_id=organization.id,
            user_id=user.id,
            role=MembershipRole.ADMIN,
            connection_id=connection.id,
            values={
                "webhook_url": "https://ops.example.com/terrasatch/events",
                "signing_secret": "shared-secret",
            },
        )
        await session.commit()

        credential = await session.scalar(
            select(IntegrationCredential).where(
                IntegrationCredential.connection_id == connection.id
            )
        )
        assert credential is not None
        assert "ops.example.com" not in credential.encrypted_payload
        assert "shared-secret" not in credential.encrypted_payload
        assert decrypt_payload(settings, credential.encrypted_payload) == {
            "webhook_url": "https://ops.example.com/terrasatch/events",
            "signing_secret": "shared-secret",
        }
        assert connected.status == IntegrationStatus.CONNECTED.value
        assert connected.provider_account_id == "ops.example.com"

    await engine.dispose()


@pytest.mark.asyncio
async def test_teams_workflows_url_is_encrypted(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii"))
    )

    async with factory() as session:
        account = Account(name="Teams integration account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Teams integration org",
            slug=f"teams-integration-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Teams Admin",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="microsoft_teams",
            scope_type="organization",
            created_by_user_id=user.id,
            display_name="Operations Teams",
            status=IntegrationStatus.REQUESTED.value,
            configuration={},
            enabled=True,
        )
        session.add(connection)
        await session.flush()

        async def fake_probe(provider, credentials, configuration):
            assert provider == "microsoft_teams"
            assert "sig=test-secret" in credentials["webhook_url"]
            return "Microsoft Teams Workflows", "prod-01.westus.logic.azure.com"

        monkeypatch.setattr(
            "terrasatch.integrations.manual_service.probe_manual_credentials",
            fake_probe,
        )
        connected = await bind_manual_credentials(
            session,
            settings,
            organization_id=organization.id,
            user_id=user.id,
            role=MembershipRole.ADMIN,
            connection_id=connection.id,
            values={
                "webhook_url": (
                    "https://prod-01.westus.logic.azure.com/workflows/abc/"
                    "triggers/manual/paths/invoke?api-version=2016-10-01&sig=test-secret"
                )
            },
        )
        await session.commit()

        credential = await session.scalar(
            select(IntegrationCredential).where(
                IntegrationCredential.connection_id == connection.id
            )
        )
        assert credential is not None
        assert "logic.azure.com" not in credential.encrypted_payload
        assert connected.provider_account_label == "Microsoft Teams Workflows"

    await engine.dispose()
