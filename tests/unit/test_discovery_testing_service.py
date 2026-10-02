"""Controlled Discovery testing service state transitions."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.database.base import Base
from terrasatch.identity.models import Account, Organization, Site, User
from terrasatch.workspace.discovery import (
    discovery_evidence_summary,
    record_discovery_event,
)
from terrasatch.workspace.discovery_testing import (
    review_workflow_test,
    start_workflow_test,
)


@pytest.mark.asyncio
async def test_controlled_test_can_be_rejected_before_sample_target_but_not_approved() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Early rejection account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Early rejection org",
            slug=f"early-reject-{uuid4().hex[:8]}",
        )
        reviewer = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Early rejection reviewer",
            enabled=True,
        )
        session.add_all([organization, reviewer])
        await session.flush()
        site = Site(
            organization_id=organization.id,
            name="Early rejection site",
            slug=f"early-reject-site-{uuid4().hex[:8]}",
        )
        session.add(site)
        await session.flush()

        workflow_key = "learn.signal.early-rejection"
        await record_discovery_event(
            session,
            organization_id=organization.id,
            site_id=site.id,
            event_type="workflow_identified",
            workflow_key=workflow_key,
            workflow_label="Candidate: Early rejection",
            source_type="satchy_pattern_detector",
            dedupe_key=f"auto:learn:{workflow_key}:support:3",
            confidence=0.65,
            evidence={"support_count": 3, "support_milestone": 3},
        )
        await start_workflow_test(
            session,
            organization_id=organization.id,
            actor_user_id=reviewer.id,
            workflow_key=workflow_key,
            request_id=uuid4(),
            objective="Check whether this candidate should continue.",
            metric_key="handoff_duration_seconds",
            metric_unit="seconds",
            baseline_value=10.0,
            target_direction="decrease",
            sample_target=3,
        )

        with pytest.raises(ValueError, match="sample target"):
            await review_workflow_test(
                session,
                organization_id=organization.id,
                actor_user_id=reviewer.id,
                workflow_key=workflow_key,
                request_id=uuid4(),
                decision="approved",
                rationale="Approval is too early.",
            )

        review_id = uuid4()
        rejected, duplicate = await review_workflow_test(
            session,
            organization_id=organization.id,
            actor_user_id=reviewer.id,
            workflow_key=workflow_key,
            request_id=review_id,
            decision="rejected",
            rationale="The controlled test should stop before more samples are collected.",
        )
        assert duplicate is False
        assert rejected.event_type == "workflow_rejected"
        assert rejected.evidence["measurement_count"] == 0
        assert rejected.evidence["execution_authorized"] is False

        retried, duplicate_retry = await review_workflow_test(
            session,
            organization_id=organization.id,
            actor_user_id=reviewer.id,
            workflow_key=workflow_key,
            request_id=review_id,
            decision="rejected",
            rationale="The controlled test should stop before more samples are collected.",
        )
        assert duplicate_retry is True
        assert retried.id == rejected.id

        with pytest.raises(ValueError, match="different Discovery evidence"):
            await review_workflow_test(
                session,
                organization_id=organization.id,
                actor_user_id=reviewer.id,
                workflow_key=workflow_key,
                request_id=review_id,
                decision="approved",
                rationale="The same review request cannot flip its decision.",
            )

        summary = await discovery_evidence_summary(
            session,
            organization_id=organization.id,
        )
        assert summary["workflow_counts"] == {
            "identified": 1,
            "testing": 0,
            "approved": 0,
            "rejected": 1,
        }
        assert summary["workflows"][0]["state"] == "rejected"
        await session.commit()

    await engine.dispose()
