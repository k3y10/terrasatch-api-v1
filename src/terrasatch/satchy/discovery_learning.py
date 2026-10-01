"""Bounded, evidence-only workflow candidate detection for Satchy Discovery."""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.workspace.discovery import (
    DiscoveryEventType,
    WORKFLOW_EVENT_TYPES,
    discovery_evidence_summary,
    record_discovery_event,
)
from terrasatch.workspace.models import WorkspaceDiscoveryEvent

_MIN_SUPPORT = 3
_SUPPORT_MILESTONES = (3, 5, 10, 20)
_MAX_PATTERNS_PER_SITE = 12
_IGNORED_EVENT_TYPES = {"GENERAL_UPDATE", "RADIO_TRANSMISSION"}
_DETECTOR_SOURCE = "satchy_pattern_detector"
_DETECTOR_VERSION = "signal-pattern-v1"


def _active_events(
    events: list[WorkspaceDiscoveryEvent],
) -> list[WorkspaceDiscoveryEvent]:
    superseded_ids = {
        event.supersedes_event_id
        for event in events
        if event.supersedes_event_id is not None
    }
    return [event for event in events if event.id not in superseded_ids]


def _signal_signature(
    event: WorkspaceDiscoveryEvent,
) -> tuple[str, tuple[str, ...]] | None:
    evidence = dict(event.evidence or {})
    source = evidence.get("source_type")
    raw_types = evidence.get("operational_event_types")
    if not isinstance(source, str) or not source.strip():
        return None
    if not isinstance(raw_types, list):
        return None

    event_types = tuple(
        sorted(
            {
                value.strip().upper()
                for value in raw_types
                if isinstance(value, str)
                and value.strip()
                and value.strip().upper() not in _IGNORED_EVENT_TYPES
            }
        )
    )
    if not event_types:
        return None
    return source.strip(), event_types


def _workflow_key(
    *,
    site_id: UUID,
    source_type: str,
    event_types: tuple[str, ...],
) -> str:
    material = f"{site_id}|{source_type}|{','.join(event_types)}"
    digest = sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"learn.signal.{digest}"


def _workflow_label(source_type: str, event_types: tuple[str, ...]) -> str:
    source = source_type.replace("_", " ").replace("-", " ").strip().title()
    event_label = " + ".join(
        event_type.replace("_", " ").title() for event_type in event_types[:3]
    )
    suffix = " + more" if len(event_types) > 3 else ""
    return f"Candidate: {source} → {event_label}{suffix} review"[:255]


def _support_milestone(support_count: int) -> int | None:
    reached = [value for value in _SUPPORT_MILESTONES if support_count >= value]
    return max(reached) if reached else None


def _confidence_for_milestone(milestone: int) -> float:
    return {
        3: 0.65,
        5: 0.72,
        10: 0.80,
        20: 0.88,
    }[milestone]


async def _active_identified_event(
    session: AsyncSession,
    *,
    organization_id: UUID,
    workflow_key: str,
) -> WorkspaceDiscoveryEvent | None:
    history = list(
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
    active = [
        event
        for event in _active_events(history)
        if event.event_type == DiscoveryEventType.WORKFLOW_IDENTIFIED.value
    ]
    return active[-1] if active else None


async def detect_discovery_workflow_candidates(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
) -> list[WorkspaceDiscoveryEvent]:
    """Identify repeatable signal patterns without testing, approving, or executing them."""

    rows = list(
        await session.scalars(
            select(WorkspaceDiscoveryEvent)
            .where(
                WorkspaceDiscoveryEvent.organization_id == organization_id,
                WorkspaceDiscoveryEvent.site_id == site_id,
                WorkspaceDiscoveryEvent.event_type.in_(
                    [
                        DiscoveryEventType.SIGNAL_OBSERVED.value,
                        DiscoveryEventType.CONTEXT_OBSERVED.value,
                    ]
                ),
            )
            .order_by(
                WorkspaceDiscoveryEvent.occurred_at.asc(),
                WorkspaceDiscoveryEvent.created_at.asc(),
            )
        )
    )
    active = _active_events(rows)
    context_events = [
        event
        for event in active
        if event.event_type == DiscoveryEventType.CONTEXT_OBSERVED.value
    ]
    if not context_events:
        return []

    grouped: dict[
        tuple[str, tuple[str, ...]],
        list[WorkspaceDiscoveryEvent],
    ] = defaultdict(list)
    for event in active:
        if event.event_type != DiscoveryEventType.SIGNAL_OBSERVED.value:
            continue
        signature = _signal_signature(event)
        if signature is not None:
            grouped[signature].append(event)

    patterns = [
        (signature, events)
        for signature, events in grouped.items()
        if len(events) >= _MIN_SUPPORT
    ]
    patterns.sort(
        key=lambda item: (
            -len(item[1]),
            item[0][0],
            item[0][1],
        )
    )
    patterns = patterns[:_MAX_PATTERNS_PER_SITE]
    if not patterns:
        return []

    summary = await discovery_evidence_summary(
        session,
        organization_id=organization_id,
    )
    workflow_states = {
        str(item["key"]): str(item["state"])
        for item in summary["workflows"]
        if isinstance(item, dict) and item.get("key") is not None
    }

    created: list[WorkspaceDiscoveryEvent] = []
    for (source_type, event_types), supporting_events in patterns:
        milestone = _support_milestone(len(supporting_events))
        if milestone is None:
            continue

        workflow_key = _workflow_key(
            site_id=site_id,
            source_type=source_type,
            event_types=event_types,
        )
        current_state = workflow_states.get(workflow_key)
        if current_state is not None and current_state != "identified":
            continue

        active_identified = await _active_identified_event(
            session,
            organization_id=organization_id,
            workflow_key=workflow_key,
        )
        previous_milestone = 0
        if active_identified is not None:
            if active_identified.source_type != _DETECTOR_SOURCE:
                continue
            prior_value = dict(active_identified.evidence or {}).get(
                "support_milestone"
            )
            if isinstance(prior_value, int):
                previous_milestone = prior_value
        if milestone <= previous_milestone:
            continue

        evidence = {
            "detector_version": _DETECTOR_VERSION,
            "site_id": str(site_id),
            "source_type": source_type,
            "operational_event_types": list(event_types),
            "support_count": len(supporting_events),
            "support_milestone": milestone,
            "context_count": len(context_events),
            "support_event_ids": [
                str(event.id) for event in supporting_events[-20:]
            ],
            "first_observed_at": supporting_events[0].occurred_at.isoformat(),
            "latest_observed_at": supporting_events[-1].occurred_at.isoformat(),
        }
        event, duplicate = await record_discovery_event(
            session,
            organization_id=organization_id,
            site_id=site_id,
            event_type=DiscoveryEventType.WORKFLOW_IDENTIFIED,
            workflow_key=workflow_key,
            workflow_label=_workflow_label(source_type, event_types),
            source_type=_DETECTOR_SOURCE,
            source_ref=f"pattern:{workflow_key}",
            dedupe_key=f"auto:learn:{workflow_key}:support:{milestone}",
            confidence=_confidence_for_milestone(milestone),
            evidence=evidence,
            supersedes_event_id=(
                active_identified.id if active_identified is not None else None
            ),
        )
        if not duplicate:
            created.append(event)
            workflow_states[workflow_key] = "identified"

    return created
