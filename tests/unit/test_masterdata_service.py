from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.database.base import Base
from terrasatch.errors import InvalidConfiguration, ResourceConflict
from terrasatch.identity.models import Account, Organization
from terrasatch.masterdata.service import (
    create_data_source,
    enqueue_source_sync,
    list_data_sources,
    list_sync_runs,
)


@pytest.mark.asyncio
async def test_source_creation_and_sync_queue_are_tenant_scoped() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        account = Account(name="Pilot")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="UAC",
            slug="uac",
            enabled=True,
        )
        session.add(organization)
        await session.flush()

        source = await create_data_source(
            session,
            organization_id=organization.id,
            name="Utah Avalanche Center",
            provider="uac",
            source_kind="avalanche_observations",
            adapter_key="manual_snapshot",
            endpoint_url="https://example.invalid/uac",
            credential_reference="oci-vault://uac-read",
            enabled=True,
        )
        run = await enqueue_source_sync(
            session,
            organization_id=organization.id,
            source_selector=str(source.id),
            trigger="test",
        )
        await session.commit()

        assert source.status == "queued"
        assert run.status == "queued"
        assert [
            item.id for item in await list_data_sources(session, organization_id=organization.id)
        ] == [source.id]
        assert [
            item.id for item in await list_sync_runs(session, organization_id=organization.id)
        ] == [run.id]

        with pytest.raises(ResourceConflict, match="active sync"):
            await enqueue_source_sync(
                session,
                organization_id=organization.id,
                source_selector=str(source.id),
                trigger="test",
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_source_configuration_rejects_raw_secret_fields() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        with pytest.raises(InvalidConfiguration, match="secret references"):
            await create_data_source(
                session,
                organization_id=uuid4(),
                name="Unsafe",
                provider="unsafe",
                source_kind="test",
                adapter_key="manual_snapshot",
                configuration={"api_key": "raw-secret"},
            )

        with pytest.raises(InvalidConfiguration, match="Credential reference"):
            await create_data_source(
                session,
                organization_id=uuid4(),
                name="Unsafe reference",
                provider="unsafe",
                source_kind="test",
                adapter_key="manual_snapshot",
                credential_reference="raw-secret-value",
            )

    await engine.dispose()
