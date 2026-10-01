"""Automatic Discovery evidence capture from canonical signals and Satchy context."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import Account, Organization, Site, User
from terrasatch.radio.schemas import TransmissionCreateRequest
from terrasatch.radio.service import ingest_transmission
from terrasatch.satchy.discovery_capture import (
    capture_workspace_context_discovery_evidence,
)
from terrasatch.workspace.discovery import discovery_evidence_summary
from terrasatch.workspace.models import WorkspaceDiscoveryEvent


@pytest.mark.asyncio
async def test_canonical_signal_and_workspace_context_are_captured_idempotently() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Automatic Discovery account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Automatic Discovery org",
            slug=f"auto-discovery-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Discovery user",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        site = Site(
            organization_id=organization.id,
            name="Automatic Discovery site",
            slug=f"auto-site-{uuid4().hex[:8]}",
        )
        session.add(site)
        await session.flush()

        settings = Settings(
            environment="local",
            intelligence_provider="deterministic",
        )
        payload = TransmissionCreateRequest(
            site_id=site.id,
            text="Recent shooting cracks below the ridgeline.",
            source="terrasatch-edge-radio",
            source_message_id="auto-discovery-signal-001",
        )
        transmission, transcript, operational_events, duplicate = await ingest_transmission(
            session,
            settings=settings,
            organization_id=organization.id,
            payload=payload,
        )
        assert duplicate is False

        signal_events = list(
            await session.scalars(
                select(WorkspaceDiscoveryEvent).where(
                    WorkspaceDiscoveryEvent.organization_id == organization.id,
                    WorkspaceDiscoveryEvent.event_type == "signal_observed",
                )
            )
        )
        assert len(signal_events) == 1
        signal = signal_events[0]
        assert signal.site_id == site.id
        assert signal.source_type == "canonical_transmission"
        assert signal.source_ref == f"transmission:{transmission.id}"
        assert signal.dedupe_key == f"auto:signal:transmission:{transmission.id}"
        assert signal.evidence == {
            "transmission_id": str(transmission.id),
            "transcript_id": str(transcript.id),
            "source_type": "terrasatch-edge-radio",
            "operational_event_count": len(operational_events),
            "operational_event_types": sorted(
                {event.event_type for event in operational_events}
            ),
            "agent_id": None,
            "channel_id": None,
        }
        assert "shooting cracks" not in str(signal.evidence).lower()

        retry = await ingest_transmission(
            session,
            settings=settings,
            organization_id=organization.id,
            payload=payload,
        )
        assert retry[3] is True
        signal_count = len(
            list(
                await session.scalars(
                    select(WorkspaceDiscoveryEvent).where(
                        WorkspaceDiscoveryEvent.organization_id == organization.id,
                        WorkspaceDiscoveryEvent.event_type == "signal_observed",
                    )
                )
            )
        )
        assert signal_count == 1

        run_id = uuid4()
        request_id = uuid4()
        first_context = await capture_workspace_context_discovery_evidence(
            session,
            organization_id=organization.id,
            site_id=site.id,
            user_id=user.id,
            run_id=run_id,
            request_id=request_id,
            active_map=True,
            field_source_count=3,
            connected_provider_count=2,
            available_capability_count=5,
        )
        assert first_context is not None
        assert first_context.evidence == {
            "run_id": str(run_id),
            "request_id": str(request_id),
            "active_map": True,
            "field_source_count": 3,
            "connected_provider_count": 2,
            "available_capability_count": 5,
        }

        repeated_context = await capture_workspace_context_discovery_evidence(
            session,
            organization_id=organization.id,
            site_id=site.id,
            user_id=user.id,
            run_id=run_id,
            request_id=request_id,
            active_map=True,
            field_source_count=3,
            connected_provider_count=2,
            available_capability_count=5,
        )
        assert repeated_context is not None
        assert repeated_context.id == first_context.id

        summary = await discovery_evidence_summary(
            session,
            organization_id=organization.id,
        )
        assert summary["event_count"] == 2
        assert summary["active_event_count"] == 2
        assert summary["signal_count"] == 1
        assert summary["context_count"] == 1
        assert summary["phase_evidence"] == {
            "listen": True,
            "watch": True,
            "learn": False,
            "adapt": False,
        }

        await session.commit()

    await engine.dispose()
