"""Evidence-backed Satchy Discovery events and derived workflow state."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.workspace.models import WorkspaceDiscoveryEvent


class DiscoveryEventType(StrEnum):
    SIGNAL_OBSERVED = "signal_observed"
    CONTEXT_OBSERVED = "context_observed"
    WORKFLOW_IDENTIFIED = "workflow_identified"
    WORKFLOW_TESTING = "workflow_testing"
    WORKFLOW_APPROVED = "workflow_approved"
    WORKFLOW_REJECTED = "workflow_rejected"


WORKFLOW_EVENT_TYPES = {
    DiscoveryEventType.WORKFLOW_IDENTIFIED.value,
    DiscoveryEventType.WORKFLOW_TESTING.value,
    DiscoveryEventType.WORKFLOW_APPROVED.value,
    DiscoveryEventType.WORKFLOW_REJECTED.value,
}

WORKFLOW_STATE_BY_EVENT = {
    DiscoveryEventType.WORKFLOW_IDENTIFIED.value: "identified",
    DiscoveryEventType.WORKFLOW_TESTING.value: "testing",
    DiscoveryEventType.WORKFLOW_APPROVED.value: "approved",
    DiscoveryEventType.WORKFLOW_REJECTED.value: "rejected",
}


def _utc_timestamp(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _is_idempotent_retry(
    existing: WorkspaceDiscoveryEvent,
    *,
    site_id: UUID | None,
    actor_user_id: UUID | None,
    supersedes_event_id: UUID | None,
    event_type: str,
    workflow_key: str | None,
    workflow_label: str | None,
    source_type: str,
    source_ref: str | None,
    confidence: float | None,
    evidence: dict[str, object],
) -> bool:
    return (
        existing.site_id == site_id
        and existing.actor_user_id == actor_user_id
        and existing.supersedes_event_id == supersedes_event_id
        and existing.event_type == event_type
        and existing.workflow_key == workflow_key
        and existing.workflow_label == workflow_label
        and existing.source_type == source_type
        and existing.source_ref == source_ref
        and existing.confidence == confidence
        and dict(existing.evidence or {}) == evidence
    )


def _logical_order_key(
    event: WorkspaceDiscoveryEvent,
    *,
    events_by_id: dict[UUID, WorkspaceDiscoveryEvent],
) -> tuple[datetime, datetime]:
    """Place a revision at the original event's position in workflow chronology."""

    current = event
    seen: set[UUID] = set()
    while current.supersedes_event_id is not None:
        if current.id in seen:
            break
        seen.add(current.id)
        parent = events_by_id.get(current.supersedes_event_id)
        if parent is None:
            break
        current = parent
    return (
        _utc_timestamp(current.occurred_at),
        _utc_timestamp(current.created_at),
    )


async def record_discovery_event(
    session: AsyncSession,
    *,
    organization_id: UUID,
    event_type: DiscoveryEventType | str,
    source_type: str,
    site_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    workflow_key: str | None = None,
    workflow_label: str | None = None,
    source_ref: str | None = None,
    dedupe_key: str | None = None,
    confidence: float | None = None,
    evidence: dict[str, object] | None = None,
    supersedes_event_id: UUID | None = None,
    occurred_at: datetime | None = None,
) -> tuple[WorkspaceDiscoveryEvent, bool]:
    """Append one evidence event, returning an existing row for an idempotent retry."""

    normalized_type = DiscoveryEventType(str(event_type)).value
    normalized_source = source_type.strip()
    if not normalized_source or len(normalized_source) > 48:
        raise ValueError("source_type must contain between 1 and 48 characters")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")

    normalized_workflow = workflow_key.strip() if workflow_key else None
    if normalized_workflow and len(normalized_workflow) > 128:
        raise ValueError("workflow_key cannot exceed 128 characters")
    if normalized_type in WORKFLOW_EVENT_TYPES and not normalized_workflow:
        raise ValueError("workflow_key is required for workflow Discovery events")

    normalized_label = workflow_label.strip() if workflow_label else None
    if normalized_label and len(normalized_label) > 255:
        raise ValueError("workflow_label cannot exceed 255 characters")

    normalized_source_ref = source_ref.strip() if source_ref else None
    if normalized_source_ref and len(normalized_source_ref) > 255:
        raise ValueError("source_ref cannot exceed 255 characters")

    normalized_dedupe = dedupe_key.strip() if dedupe_key else None
    if normalized_dedupe and len(normalized_dedupe) > 255:
        raise ValueError("dedupe_key cannot exceed 255 characters")

    evidence_payload = dict(evidence or {})
    if len(evidence_payload) > 32:
        raise ValueError("Discovery evidence supports at most 32 fields")
    try:
        encoded_evidence = json.dumps(
            evidence_payload,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Discovery evidence must be JSON-serializable") from exc
    if len(encoded_evidence.encode("utf-8")) > 16_384:
        raise ValueError("Discovery evidence cannot exceed 16 KiB")

    effective_occurred_at = occurred_at or datetime.now(UTC)

    if normalized_dedupe:
        existing = await session.scalar(
            select(WorkspaceDiscoveryEvent).where(
                WorkspaceDiscoveryEvent.organization_id == organization_id,
                WorkspaceDiscoveryEvent.dedupe_key == normalized_dedupe,
            )
        )
        if existing is not None:
            if not _is_idempotent_retry(
                existing,
                site_id=site_id,
                actor_user_id=actor_user_id,
                supersedes_event_id=supersedes_event_id,
                event_type=normalized_type,
                workflow_key=normalized_workflow,
                workflow_label=normalized_label,
                source_type=normalized_source,
                source_ref=normalized_source_ref,
                confidence=confidence,
                evidence=evidence_payload,
            ):
                raise ValueError(
                    "dedupe_key is already used by different Discovery evidence"
                )
            return existing, True

    superseded: WorkspaceDiscoveryEvent | None = None
    if supersedes_event_id is not None:
        superseded = await session.scalar(
            select(WorkspaceDiscoveryEvent).where(
                WorkspaceDiscoveryEvent.id == supersedes_event_id,
                WorkspaceDiscoveryEvent.organization_id == organization_id,
            )
        )
        if superseded is None:
            raise ValueError("superseded Discovery event was not found in this organization")

        if superseded.event_type != normalized_type:
            raise ValueError("Discovery revisions must keep the same event_type")
        if normalized_type in WORKFLOW_EVENT_TYPES:
            if superseded.workflow_key != normalized_workflow:
                raise ValueError("workflow revisions must keep the same workflow_key")

        prior_successor = await session.scalar(
            select(WorkspaceDiscoveryEvent).where(
                WorkspaceDiscoveryEvent.organization_id == organization_id,
                WorkspaceDiscoveryEvent.supersedes_event_id == supersedes_event_id,
            )
        )
        if prior_successor is not None:
            raise ValueError("Discovery event has already been superseded")

        superseded_at = _utc_timestamp(superseded.occurred_at)
        compare_at = _utc_timestamp(effective_occurred_at)
        if compare_at < superseded_at:
            raise ValueError("Discovery revision cannot occur before the superseded event")

    event = WorkspaceDiscoveryEvent(
        organization_id=organization_id,
        site_id=site_id,
        actor_user_id=actor_user_id,
        supersedes_event_id=supersedes_event_id,
        event_type=normalized_type,
        workflow_key=normalized_workflow,
        workflow_label=normalized_label,
        source_type=normalized_source,
        source_ref=normalized_source_ref,
        dedupe_key=normalized_dedupe,
        confidence=confidence,
        evidence=evidence_payload,
        occurred_at=effective_occurred_at,
    )
    if normalized_dedupe or supersedes_event_id is not None:
        try:
            async with session.begin_nested():
                session.add(event)
                await session.flush()
        except IntegrityError:
            if normalized_dedupe:
                existing = await session.scalar(
                    select(WorkspaceDiscoveryEvent).where(
                        WorkspaceDiscoveryEvent.organization_id == organization_id,
                        WorkspaceDiscoveryEvent.dedupe_key == normalized_dedupe,
                    )
                )
                if existing is not None:
                    if not _is_idempotent_retry(
                        existing,
                        site_id=site_id,
                        actor_user_id=actor_user_id,
                        supersedes_event_id=supersedes_event_id,
                        event_type=normalized_type,
                        workflow_key=normalized_workflow,
                        workflow_label=normalized_label,
                        source_type=normalized_source,
                        source_ref=normalized_source_ref,
                        confidence=confidence,
                        evidence=evidence_payload,
                    ):
                        raise ValueError(
                            "dedupe_key is already used by different Discovery evidence"
                        ) from None
                    return existing, True
            if supersedes_event_id is not None:
                successor = await session.scalar(
                    select(WorkspaceDiscoveryEvent).where(
                        WorkspaceDiscoveryEvent.organization_id == organization_id,
                        WorkspaceDiscoveryEvent.supersedes_event_id == supersedes_event_id,
                    )
                )
                if successor is not None:
                    raise ValueError("Discovery event has already been superseded") from None
            raise
    else:
        session.add(event)
        await session.flush()

    await session.refresh(event)
    return event, False


async def list_discovery_events(
    session: AsyncSession,
    *,
    organization_id: UUID,
    event_type: DiscoveryEventType | str | None = None,
    workflow_key: str | None = None,
    limit: int = 100,
) -> list[WorkspaceDiscoveryEvent]:
    query = select(WorkspaceDiscoveryEvent).where(
        WorkspaceDiscoveryEvent.organization_id == organization_id
    )
    if event_type is not None:
        query = query.where(
            WorkspaceDiscoveryEvent.event_type == DiscoveryEventType(str(event_type)).value
        )
    if workflow_key is not None:
        query = query.where(WorkspaceDiscoveryEvent.workflow_key == workflow_key)
    return list(
        await session.scalars(
            query.order_by(
                WorkspaceDiscoveryEvent.occurred_at.desc(),
                WorkspaceDiscoveryEvent.created_at.desc(),
            ).limit(limit)
        )
    )


def discovery_event_payload(event: WorkspaceDiscoveryEvent) -> dict[str, object]:
    return {
        "id": str(event.id),
        "organization_id": str(event.organization_id),
        "site_id": str(event.site_id) if event.site_id else None,
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "supersedes_event_id": (
            str(event.supersedes_event_id) if event.supersedes_event_id else None
        ),
        "event_type": event.event_type,
        "workflow_key": event.workflow_key,
        "workflow_label": event.workflow_label,
        "source_type": event.source_type,
        "source_ref": event.source_ref,
        "dedupe_key": event.dedupe_key,
        "confidence": event.confidence,
        "evidence": dict(event.evidence or {}),
        "occurred_at": event.occurred_at,
        "created_at": event.created_at,
    }


async def discovery_evidence_summary(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> dict[str, object]:
    """Derive workflow counts and phase evidence from append-only events."""

    events = list(
        await session.scalars(
            select(WorkspaceDiscoveryEvent)
            .where(WorkspaceDiscoveryEvent.organization_id == organization_id)
            .order_by(
                WorkspaceDiscoveryEvent.occurred_at.asc(),
                WorkspaceDiscoveryEvent.created_at.asc(),
            )
        )
    )

    events_by_id = {event.id: event for event in events}
    superseded_ids = {
        event.supersedes_event_id
        for event in events
        if event.supersedes_event_id is not None
    }
    effective_events = [
        event for event in events if event.id not in superseded_ids
    ]
    effective_events.sort(
        key=lambda event: _logical_order_key(
            event,
            events_by_id=events_by_id,
        )
    )

    signal_count = 0
    context_count = 0
    adapt_evidence = False
    workflow_states: dict[str, dict[str, object]] = {}

    for event in effective_events:
        if event.event_type == DiscoveryEventType.SIGNAL_OBSERVED.value:
            signal_count += 1
        elif event.event_type == DiscoveryEventType.CONTEXT_OBSERVED.value:
            context_count += 1

        if event.event_type in {
            DiscoveryEventType.WORKFLOW_TESTING.value,
            DiscoveryEventType.WORKFLOW_APPROVED.value,
            DiscoveryEventType.WORKFLOW_REJECTED.value,
        }:
            adapt_evidence = True

        state = WORKFLOW_STATE_BY_EVENT.get(event.event_type)
        if state is None or event.workflow_key is None:
            continue
        previous = workflow_states.get(event.workflow_key)
        previous_label = previous.get("label") if previous is not None else None
        workflow_states[event.workflow_key] = {
            "key": event.workflow_key,
            "label": event.workflow_label or previous_label,
            "state": state,
            "latest_event_id": str(event.id),
            "latest_event_at": event.occurred_at,
        }

    identified = len(workflow_states)
    testing = sum(item["state"] == "testing" for item in workflow_states.values())
    approved = sum(item["state"] == "approved" for item in workflow_states.values())
    rejected = sum(item["state"] == "rejected" for item in workflow_states.values())

    return {
        "event_count": len(events),
        "active_event_count": len(effective_events),
        "signal_count": signal_count,
        "context_count": context_count,
        "workflow_counts": {
            "identified": identified,
            "testing": testing,
            "approved": approved,
            "rejected": rejected,
        },
        "phase_evidence": {
            "listen": signal_count > 0,
            "watch": context_count > 0,
            "learn": identified > 0,
            "adapt": adapt_evidence,
        },
        "latest_event_at": events[-1].occurred_at if events else None,
        "workflows": sorted(
            workflow_states.values(),
            key=lambda item: (
                str(item["state"]),
                str(item["label"] or item["key"]),
            ),
        ),
    }
