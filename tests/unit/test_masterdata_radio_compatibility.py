import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.auth import models as auth_models
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.edge import models as edge_models
from terrasatch.identity.models import Account, Organization, Site
from terrasatch.masterdata import models as masterdata_models
from terrasatch.radio.schemas import TransmissionCreateRequest
from terrasatch.radio.service import ingest_transmission

_MODEL_MODULES = (auth_models, edge_models, masterdata_models)


@pytest.mark.asyncio
async def test_existing_edge_radio_pipeline_survives_additive_spatial_schema() -> None:
    assert _MODEL_MODULES
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        account = Account(name="Compatibility")
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
        site = Site(
            organization_id=organization.id,
            name="Salt Lake",
            slug="salt-lake",
            enabled=True,
        )
        session.add(site)
        await session.flush()

        transmission, transcript, events, duplicate = await ingest_transmission(
            session,
            settings=Settings(intelligence_provider="deterministic"),
            organization_id=organization.id,
            payload=TransmissionCreateRequest(
                site_id=site.id,
                text=(
                    "Patrol 4 reports shooting cracks at Cardiff Bowl on a northeast aspect "
                    "around 9,800 feet. No avalanche observed."
                ),
                source="terrasatch-edge-stt",
                source_message_id="phase1-edge-compatibility",
                transcript_provider="faster_whisper",
                transcript_model="base.en",
            ),
        )
        await session.commit()

        assert duplicate is False
        assert transmission.source_type == "terrasatch-edge-stt"
        assert transcript.provider == "faster_whisper"
        assert events
        assert events[0].transmission_id == transmission.id
        assert events[0].transcript_id == transcript.id
        assert events[0].region_id is None
        assert events[0].terrain_cell_id is None
        assert events[0].spatial_status is None

    await engine.dispose()
