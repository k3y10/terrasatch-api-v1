"""Controlled testing helpers for Discovery workflow candidates."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.workspace.discovery import (
    DiscoveryEventType,
    discovery_evidence_summary,
    record_discovery_event,
)
from terrasatch.workspace.models import WorkspaceDiscoveryEvent

_TEST_SOURCE = "controlled_test"
_MEASUREMENT_SOURCE = "test_measurement"
_REVIEW_SOURCE = "human_review"


async def _workflow_history(
    session: AsyncSession,
    *,
    organization_id: UUID,
    workflow_key: str,
) -> list[WorkspaceDiscoveryEvent]:
    return list(
        await session.scalars(
            select(WorkspaceDiscoveryEvent)
            .where(
                WorkspaceDiscoveryEvent.organization_id == organization_id,
                WorkspaceDiscoveryEvent.workflow_key == workflow_key,
            )
            .order_by(
                WorkspaceDiscoveryEvent.occurred_at.asc(),
                WorkspaceDiscoveryEvent.created_at.asc(),
            )
        )
    )


def _active_events(
    history: list[WorkspaceDiscoveryEvent],
) -> list[WorkspaceDiscoveryEvent]:
    superseded_ids = {
        event.supersedes_event_id
        for event in history
        if event.supersedes_event_id is not None
    }
    return [event for event in history if event.id not in superseded_ids]


async def _current_workflow(
    session: AsyncSession,
    *,
    organization_id: UUID,
    workflow_key: str,
) -> dict[str, object] | None:
    summary = await discovery_evidence_summary(
        session,
        organization_id=organization_id,
    )
    return next(
        (
            item
            for item in summary["workflows"]
            if isinstance(item, dict) and item.get("key") == workflow_key
        ),
        None,
    )


async def _active_event(
    session: AsyncSession,
    *,
    organization_id: UUID,
    workflow_key: str,
    event_type: DiscoveryEventType,
) -> WorkspaceDiscoveryEvent | None:
    history = await _workflow_history(
        session,
        organization_id=organization_id,
        workflow_key=workflow_key,
    )
    active = [
        event
        for event in _active_events(history)
        if event.event_type == event_type.value
    ]
    return active[-1] if active else None


async def _existing_request(
    session: AsyncSession,
    *,
    organization_id: UUID,
    dedupe_key: str,
    event_type: DiscoveryEventType,
    workflow_key: str,
) -> WorkspaceDiscoveryEvent | None:
    existing = await session.scalar(
        select(WorkspaceDiscoveryEvent).where(
            WorkspaceDiscoveryEvent.organization_id == organization_id,
            WorkspaceDiscoveryEvent.dedupe_key == dedupe_key,
        )
    )
    if existing is None:
        return None
    if (
        existing.event_type != event_type.value
        or existing.workflow_key != workflow_key
    ):
        raise ValueError("request_id is already used by different Discovery evidence")
    return existing


async def start_workflow_test(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    workflow_key: str,
    request_id: UUID,
    objective: str,
    metric_key: str,
    metric_unit: str,
    baseline_value: float,
    target_direction: str,
    sample_target: int,
) -> tuple[WorkspaceDiscoveryEvent, bool]:
    if not math.isfinite(baseline_value):
        raise ValueError("baseline_value must be finite")

    dedupe_key = f"controlled-test:{workflow_key}:{request_id}"
    existing = await _existing_request(
        session,
        organization_id=organization_id,
        dedupe_key=dedupe_key,
        event_type=DiscoveryEventType.WORKFLOW_TESTING,
        workflow_key=workflow_key,
    )
    if existing is not None:
        return existing, True

    workflow = await _current_workflow(
        session,
        organization_id=organization_id,
        workflow_key=workflow_key,
    )
    if workflow is None:
        raise ValueError("workflow candidate was not found")
    if workflow["state"] != "identified":
        raise ValueError("workflow must be identified before controlled testing can start")

    identified = await _active_event(
        session,
        organization_id=organization_id,
        workflow_key=workflow_key,
        event_type=DiscoveryEventType.WORKFLOW_IDENTIFIED,
    )
    if identified is None:
        raise ValueError("active workflow candidate evidence was not found")

    evidence = {
        "test_request_id": str(request_id),
        "candidate_event_id": str(identified.id),
        "objective": objective.strip(),
        "metric_key": metric_key.strip(),
        "metric_unit": metric_unit.strip(),
        "baseline_value": baseline_value,
        "target_direction": target_direction,
        "sample_target": sample_target,
        "measurement_count": 0,
        "measurements": [],
        "measured_average": None,
        "observed_delta_from_baseline": None,
        "observed_delta_percent": None,
        "sample_target_met": False,
        "execution_authorized": False,
    }
    return await record_discovery_event(
        session,
        organization_id=organization_id,
        site_id=identified.site_id,
        actor_user_id=actor_user_id,
        event_type=DiscoveryEventType.WORKFLOW_TESTING,
        workflow_key=workflow_key,
        workflow_label=identified.workflow_label,
        source_type=_TEST_SOURCE,
        source_ref=f"candidate:{identified.id}",
        dedupe_key=dedupe_key,
        evidence=evidence,
    )


async def record_workflow_test_measurement(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    workflow_key: str,
    measurement_id: UUID,
    value: float,
    note: str | None = None,
    source_ref: str | None = None,
) -> tuple[WorkspaceDiscoveryEvent, bool]:
    if not math.isfinite(value):
        raise ValueError("measurement value must be finite")

    dedupe_key = f"test-measurement:{workflow_key}:{measurement_id}"
    existing = await _existing_request(
        session,
        organization_id=organization_id,
        dedupe_key=dedupe_key,
        event_type=DiscoveryEventType.WORKFLOW_TESTING,
        workflow_key=workflow_key,
    )
    if existing is not None:
        return existing, True

    workflow = await _current_workflow(
        session,
        organization_id=organization_id,
        workflow_key=workflow_key,
    )
    if workflow is None or workflow["state"] != "testing":
        raise ValueError("workflow must be in testing before measurements can be recorded")

    active_test = await _active_event(
        session,
        organization_id=organization_id,
        workflow_key=workflow_key,
        event_type=DiscoveryEventType.WORKFLOW_TESTING,
    )
    if active_test is None:
        raise ValueError("active workflow testing evidence was not found")
    if active_test.source_type not in {_TEST_SOURCE, _MEASUREMENT_SOURCE}:
        raise ValueError("workflow testing evidence is not a controlled TerraSatch test")

    evidence = dict(active_test.evidence or {})
    measurements = list(evidence.get("measurements") or [])
    sample_target = int(evidence.get("sample_target") or 1)
    if len(measurements) >= sample_target:
        raise ValueError("test sample target has already been met")

    measurement = {
        "measurement_id": str(measurement_id),
        "value": value,
        "recorded_by": str(actor_user_id),
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    if note:
        measurement["note"] = note.strip()
    if source_ref:
        measurement["source_ref"] = source_ref.strip()
    measurements.append(measurement)

    values = [float(item["value"]) for item in measurements]
    average = sum(values) / len(values)
    baseline = float(evidence["baseline_value"])
    delta = average - baseline
    delta_percent = None if baseline == 0 else (delta / abs(baseline)) * 100

    evidence.update(
        {
            "measurement_count": len(measurements),
            "measurements": measurements,
            "measured_average": average,
            "observed_delta_from_baseline": delta,
            "observed_delta_percent": delta_percent,
            "sample_target_met": len(measurements) >= sample_target,
            "execution_authorized": False,
        }
    )
    return await record_discovery_event(
        session,
        organization_id=organization_id,
        site_id=active_test.site_id,
        actor_user_id=actor_user_id,
        event_type=DiscoveryEventType.WORKFLOW_TESTING,
        workflow_key=workflow_key,
        workflow_label=active_test.workflow_label,
        source_type=_MEASUREMENT_SOURCE,
        source_ref=source_ref or f"measurement:{measurement_id}",
        dedupe_key=dedupe_key,
        evidence=evidence,
        supersedes_event_id=active_test.id,
    )
