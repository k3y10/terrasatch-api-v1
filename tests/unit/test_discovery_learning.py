"""Bounded workflow-pattern learning for Satchy Discovery."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.database.base import Base
from terrasatch.identity.models import Account, Organization, Site, User
from terrasatch.satchy.discovery_learning import detect_discovery_workflow_candidates
from terrasatch.workspace.discovery import (
    discovery_evidence_summary,
    record_discovery_event,
)
from terrasatch.workspace.models import WorkspaceDiscoveryEvent


async def _signal(
    session,
    *,
    organization_id,
    site_id,
    index: int,
    event_type: str = "OBSERVATION",
) -> WorkspaceDiscoveryEvent:
    event, duplicate = await record_discovery_event(
        session,
        organization_id=organization_id,
        site_id=site_id,
        event_type="signal_observed",
        source_type="canonical_transmission",
        source_ref=f"transmission:signal-{index}",
        dedupe_key=f"auto:signal:transmission:signal-{index}",
        evidence={
            "transmission_id": f"signal-{index}",
            "transcript_id": f"transcript-{index}",
            "source_type": "terrasatch-edge-radio",
            "operational_event_count": 1,
            "operational_event_types": [event_type],
            "agent_id": None,
            "channel_id": None,
        },
    )
    assert duplicate is False
    return event


@pytest.mark.asyncio
async def test_learning_requires_repetition_and_revises_at_bounded_milestones() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Discovery learning account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Discovery learning org",
            slug=f"learn-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Discovery reviewer",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        site = Site(
            organization_id=organization.id,
            name="Learning site",
            slug=f"learn-site-{uuid4().hex[:8]}",
        )
        session.add(site)
        await session.flush()

        await record_discovery_event(
            session,
            organization_id=organization.id,
            site_id=site.id,
            actor_user_id=user.id,
            event_type="context_observed",
            source_type="satchy_workspace",
            source_ref="satchy_run:learn-context",
            dedupe_key="auto:context:satchy_run:learn-context",
            evidence={
                "run_id": "learn-context",
                "request_id": "learn-request",
                "active_map": True,
                "field_source_count": 2,
                "connected_provider_count": 1,
                "available_capability_count": 3,
            },
        )

        await _signal(
            session,
            organization_id=organization.id,
            site_id=site.id,
            index=1,
        )
        await _signal(
            session,
            organization_id=organization.id,
            site_id=site.id,
            index=2,
        )
        assert await detect_discovery_workflow_candidates(
            session,
            organization_id=organization.id,
            site_id=site.id,
        ) == []

        await _signal(
            session,
            organization_id=organization.id,
            site_id=site.id,
            index=3,
        )
        initial = await detect_discovery_workflow_candidates(
            session,
            organization_id=organization.id,
            site_id=site.id,
        )
        assert len(initial) == 1
        identified = initial[0]
        assert identified.event_type == "workflow_identified"
        assert identified.source_type == "satchy_pattern_detector"
        assert identified.workflow_key is not None
        assert identified.workflow_label is not None
        assert identified.workflow_label.startswith("Candidate:")
        assert identified.confidence == 0.65
        assert identified.evidence["support_count"] == 3
        assert identified.evidence["support_milestone"] == 3
        assert identified.evidence["operational_event_types"] == ["OBSERVATION"]
        assert len(identified.evidence["support_event_ids"]) == 3

        assert await detect_discovery_workflow_candidates(
            session,
            organization_id=organization.id,
            site_id=site.id,
        ) == []

        await _signal(
            session,
            organization_id=organization.id,
            site_id=site.id,
            index=4,
        )
        assert await detect_discovery_workflow_candidates(
            session,
            organization_id=organization.id,
            site_id=site.id,
        ) == []
        await _signal(
            session,
            organization_id=organization.id,
            site_id=site.id,
            index=5,
        )
        revised = await detect_discovery_workflow_candidates(
            session,
            organization_id=organization.id,
            site_id=site.id,
        )
        assert len(revised) == 1
        revision = revised[0]
        assert revision.supersedes_event_id == identified.id
        assert revision.workflow_key == identified.workflow_key
        assert revision.confidence == 0.72
        assert revision.evidence["support_count"] == 5
        assert revision.evidence["support_milestone"] == 5

        summary = await discovery_evidence_summary(
            session,
            organization_id=organization.id,
        )
        assert summary["workflow_counts"] == {
            "identified": 1,
            "testing": 0,
            "approved": 0,
            "rejected": 0,
        }
        workflow = summary["workflows"][0]
        assert workflow["key"] == identified.workflow_key
        assert workflow["state"] == "identified"
        assert workflow["revision_count"] == 1

        testing, duplicate = await record_discovery_event(
            session,
            organization_id=organization.id,
            site_id=site.id,
            actor_user_id=user.id,
            event_type="workflow_testing",
            workflow_key=identified.workflow_key,
            workflow_label=identified.workflow_label,
            source_type="manual",
            source_ref="review:testing",
            dedupe_key=f"manual:{identified.workflow_key}:testing",
            evidence={"reason": "Reviewer started controlled testing"},
        )
        assert duplicate is False
        assert testing.event_type == "workflow_testing"

        for index in range(6, 11):
            await _signal(
                session,
                organization_id=organization.id,
                site_id=site.id,
                index=index,
            )
        assert await detect_discovery_workflow_candidates(
            session,
            organization_id=organization.id,
            site_id=site.id,
        ) == []

        identified_rows = list(
            await session.scalars(
                select(WorkspaceDiscoveryEvent).where(
                    WorkspaceDiscoveryEvent.organization_id == organization.id,
                    WorkspaceDiscoveryEvent.workflow_key == identified.workflow_key,
                    WorkspaceDiscoveryEvent.event_type == "workflow_identified",
                )
            )
        )
        assert len(identified_rows) == 2

        final_summary = await discovery_evidence_summary(
            session,
            organization_id=organization.id,
        )
        assert final_summary["workflow_counts"] == {
            "identified": 1,
            "testing": 1,
            "approved": 0,
            "rejected": 0,
        }
        assert final_summary["workflows"][0]["state"] == "testing"

        await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_learning_ignores_generic_signals_without_specific_event_pattern() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Generic learning account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Generic learning org",
            slug=f"generic-learn-{uuid4().hex[:8]}",
        )
        session.add(organization)
        await session.flush()
        site = Site(
            organization_id=organization.id,
            name="Generic site",
            slug=f"generic-site-{uuid4().hex[:8]}",
        )
        session.add(site)
        await session.flush()

        await record_discovery_event(
            session,
            organization_id=organization.id,
            site_id=site.id,
            event_type="context_observed",
            source_type="satchy_workspace",
            source_ref="satchy_run:generic-context",
            dedupe_key="auto:context:satchy_run:generic-context",
            evidence={},
        )
        for index in range(1, 5):
            await _signal(
                session,
                organization_id=organization.id,
                site_id=site.id,
                index=index,
                event_type="GENERAL_UPDATE",
            )

        created = await detect_discovery_workflow_candidates(
            session,
            organization_id=organization.id,
            site_id=site.id,
        )
        assert created == []

        summary = await discovery_evidence_summary(
            session,
            organization_id=organization.id,
        )
        assert summary["phase_evidence"]["listen"] is True
        assert summary["phase_evidence"]["watch"] is True
        assert summary["phase_evidence"]["learn"] is False
        assert summary["workflow_counts"]["identified"] == 0

        await session.commit()

    await engine.dispose()
