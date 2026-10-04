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


def _clean_text(value: str, *, field: str, max_length: int) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_length:
        raise ValueError(f"{field} must contain between 1 and {max_length} characters")
    return cleaned


def _same_number(left: object, right: float) -> bool:
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


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
    objective = _clean_text(objective, field="objective", max_length=500)
    metric_key = _clean_text(metric_key, field="metric_key", max_length=64)
    metric_unit = _clean_text(metric_unit, field="metric_unit", max_length=32)
    if target_direction not in {"decrease", "increase", "maintain"}:
        raise ValueError("target_direction is invalid")
    if not 1 <= sample_target <= 20:
        raise ValueError("sample_target must be between 1 and 20")

    dedupe_key = f"controlled-test:{workflow_key}:{request_id}"
    existing = await _existing_request(
        session,
        organization_id=organization_id,
        dedupe_key=dedupe_key,
        event_type=DiscoveryEventType.WORKFLOW_TESTING,
        workflow_key=workflow_key,
    )
    if existing is not None:
        prior = dict(existing.evidence or {})
        if existing.actor_user_id != actor_user_id:
            raise ValueError("request_id is already used by a different actor")
        if not (
            prior.get("objective") == objective
            and prior.get("metric_key") == metric_key
            and prior.get("metric_unit") == metric_unit
            and _same_number(prior.get("baseline_value"), baseline_value)
            and prior.get("target_direction") == target_direction
            and prior.get("sample_target") == sample_target
        ):
            raise ValueError("request_id is already used by different test content")
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
        "objective": objective,
        "metric_key": metric_key,
        "metric_unit": metric_unit,
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
    clean_note = (
        _clean_text(note, field="note", max_length=240)
        if note is not None
        else None
    )
    clean_source_ref = (
        _clean_text(source_ref, field="source_ref", max_length=255)
        if source_ref is not None
        else None
    )

    dedupe_key = f"test-measurement:{workflow_key}:{measurement_id}"
    existing = await _existing_request(
        session,
        organization_id=organization_id,
        dedupe_key=dedupe_key,
        event_type=DiscoveryEventType.WORKFLOW_TESTING,
        workflow_key=workflow_key,
    )
    if existing is not None:
        if existing.actor_user_id != actor_user_id:
            raise ValueError("measurement_id is already used by a different actor")
        measurements = list(dict(existing.evidence or {}).get("measurements") or [])
        prior = next(
            (
                item
                for item in measurements
                if isinstance(item, dict)
                and item.get("measurement_id") == str(measurement_id)
            ),
            None,
        )
        if prior is None or not _same_number(prior.get("value"), value):
            raise ValueError("measurement_id is already used by different content")
        if (prior.get("note") or None) != clean_note:
            raise ValueError("measurement_id is already used by different content")
        if (prior.get("source_ref") or None) != clean_source_ref:
            raise ValueError("measurement_id is already used by different content")
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
    if clean_note:
        measurement["note"] = clean_note
    if clean_source_ref:
        measurement["source_ref"] = clean_source_ref
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
        source_ref=clean_source_ref or f"measurement:{measurement_id}",
        dedupe_key=dedupe_key,
        evidence=evidence,
        supersedes_event_id=active_test.id,
    )


async def review_workflow_test(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    workflow_key: str,
    request_id: UUID,
    decision: str,
    rationale: str,
) -> tuple[WorkspaceDiscoveryEvent, bool]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    rationale = _clean_text(rationale, field="rationale", max_length=1000)
    event_type = (
        DiscoveryEventType.WORKFLOW_APPROVED
        if decision == "approved"
        else DiscoveryEventType.WORKFLOW_REJECTED
    )
    dedupe_key = f"test-review:{workflow_key}:{request_id}"
    existing = await _existing_request(
        session,
        organization_id=organization_id,
        dedupe_key=dedupe_key,
        event_type=event_type,
        workflow_key=workflow_key,
    )
    if existing is not None:
        if existing.actor_user_id != actor_user_id:
            raise ValueError("request_id is already used by a different actor")
        prior = dict(existing.evidence or {})
        if (
            prior.get("decision") != decision
            or prior.get("rationale") != rationale
        ):
            raise ValueError("request_id is already used by different review content")
        return existing, True

    workflow = await _current_workflow(
        session,
        organization_id=organization_id,
        workflow_key=workflow_key,
    )
    if workflow is None or workflow["state"] != "testing":
        raise ValueError("workflow must be in testing before review")

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

    test_evidence = dict(active_test.evidence or {})
    measurement_count = int(test_evidence.get("measurement_count") or 0)
    sample_target = int(test_evidence.get("sample_target") or 1)
    if decision == "approved" and measurement_count < sample_target:
        raise ValueError("approval requires the declared sample target to be met")

    evidence = {
        "review_request_id": str(request_id),
        "testing_event_id": str(active_test.id),
        "decision": decision,
        "rationale": rationale,
        "objective": test_evidence.get("objective"),
        "metric_key": test_evidence.get("metric_key"),
        "metric_unit": test_evidence.get("metric_unit"),
        "baseline_value": test_evidence.get("baseline_value"),
        "target_direction": test_evidence.get("target_direction"),
        "measurement_count": measurement_count,
        "sample_target": sample_target,
        "measured_average": test_evidence.get("measured_average"),
        "observed_delta_from_baseline": test_evidence.get(
            "observed_delta_from_baseline"
        ),
        "observed_delta_percent": test_evidence.get("observed_delta_percent"),
        "sample_target_met": measurement_count >= sample_target,
        "execution_authorized": False,
    }
    return await record_discovery_event(
        session,
        organization_id=organization_id,
        site_id=active_test.site_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        workflow_key=workflow_key,
        workflow_label=active_test.workflow_label,
        source_type=_REVIEW_SOURCE,
        source_ref=f"testing:{active_test.id}",
        dedupe_key=dedupe_key,
        evidence=evidence,
    )
