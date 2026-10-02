"""Best-effort automatic evidence capture for Satchy Discovery."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.radio.models import OperationalEvent, Transcript, Transmission
from terrasatch.satchy.discovery_learning import detect_discovery_workflow_candidates
from terrasatch.workspace.discovery import record_discovery_event
from terrasatch.workspace.models import WorkspaceDiscoveryEvent

logger = structlog.get_logger(__name__)


async def capture_transmission_discovery_evidence(
    session: AsyncSession,
    *,
    transmission: Transmission,
    transcript: Transcript,
    events: Sequence[OperationalEvent],
) -> WorkspaceDiscoveryEvent | None:
    """Record that a canonical field signal was observed without copying raw source text."""

    evidence = {
        "transmission_id": str(transmission.id),
        "transcript_id": str(transcript.id),
        "source_type": transmission.source_type,
        "operational_event_count": len(events),
        "operational_event_types": sorted({event.event_type for event in events}),
        "agent_id": str(transmission.agent_id) if transmission.agent_id else None,
        "channel_id": str(transmission.channel_id) if transmission.channel_id else None,
    }
    try:
        async with session.begin_nested():
            event, duplicate = await record_discovery_event(
                session,
                organization_id=transmission.organization_id,
                site_id=transmission.site_id,
                event_type="signal_observed",
                source_type="canonical_transmission",
                source_ref=f"transmission:{transmission.id}",
                dedupe_key=f"auto:signal:transmission:{transmission.id}",
                evidence=evidence,
                occurred_at=transmission.received_at,
            )
    except Exception as exc:  # Discovery evidence must never break canonical ingestion.
        logger.warning(
            "discovery_signal_capture_failed",
            organization_id=str(transmission.organization_id),
            transmission_id=str(transmission.id),
            error=str(exc),
        )
        return None

    if not duplicate:
        try:
            async with session.begin_nested():
                await detect_discovery_workflow_candidates(
                    session,
                    organization_id=transmission.organization_id,
                    site_id=transmission.site_id,
                )
        except Exception as exc:  # LEARN must never break LISTEN or canonical ingestion.
            logger.warning(
                "discovery_learning_failed",
                organization_id=str(transmission.organization_id),
                site_id=str(transmission.site_id),
                trigger="signal",
                error=str(exc),
            )
    return event


async def capture_workspace_context_discovery_evidence(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
    user_id: UUID,
    run_id: UUID,
    request_id: UUID,
    active_map: bool,
    field_source_count: int,
    connected_provider_count: int,
    available_capability_count: int,
) -> WorkspaceDiscoveryEvent | None:
    """Record authorized workspace context use without storing messages or map coordinates."""

    evidence = {
        "run_id": str(run_id),
        "request_id": str(request_id),
        "active_map": active_map,
        "field_source_count": max(field_source_count, 0),
        "connected_provider_count": max(connected_provider_count, 0),
        "available_capability_count": max(available_capability_count, 0),
    }
    try:
        async with session.begin_nested():
            event, duplicate = await record_discovery_event(
                session,
                organization_id=organization_id,
                site_id=site_id,
                actor_user_id=user_id,
                event_type="context_observed",
                source_type="satchy_workspace",
                source_ref=f"satchy_run:{run_id}",
                dedupe_key=f"auto:context:satchy_run:{run_id}",
                evidence=evidence,
            )
    except Exception as exc:  # Context evidence is observational, never request-critical.
        logger.warning(
            "discovery_context_capture_failed",
            organization_id=str(organization_id),
            run_id=str(run_id),
            error=str(exc),
        )
        return None

    if not duplicate:
        try:
            async with session.begin_nested():
                await detect_discovery_workflow_candidates(
                    session,
                    organization_id=organization_id,
                    site_id=site_id,
                )
        except Exception as exc:  # LEARN must never break WATCH or Satchy requests.
            logger.warning(
                "discovery_learning_failed",
                organization_id=str(organization_id),
                site_id=str(site_id),
                trigger="context",
                error=str(exc),
            )
    return event
