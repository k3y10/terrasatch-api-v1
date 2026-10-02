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
