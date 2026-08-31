"""Deterministic callsign enrichment and radio conversation association."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.radio.addressing import (
    AddressingResolution,
    CallsignCandidate,
    parse_radio_addressing,
)
from terrasatch.radio.models import (
    Agent,
    Callsign,
    OperationalEvent,
    RadioConversation,
    Transmission,
)


async def _callsign_candidates(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
) -> list[CallsignCandidate]:
    items = list(
        await session.scalars(
            select(Callsign).where(
                Callsign.organization_id == organization_id,
                Callsign.enabled.is_(True),
                or_(Callsign.site_id == site_id, Callsign.site_id.is_(None)),
            )
        )
    )
    return [
        CallsignCandidate(id=item.id, name=item.name, aliases=tuple(item.aliases or []))
        for item in items
    ]


async def _agent_names(
    session: AsyncSession,
    *,
    transmission: Transmission,
) -> set[str]:
    names = {"Satchy"}
    if transmission.agent_id is not None:
        agent = await session.scalar(
            select(Agent).where(
                Agent.id == transmission.agent_id,
                Agent.organization_id == transmission.organization_id,
            )
        )
        if agent is not None:
            names.add(agent.name)
    return names


def _participant_identity(resolution: AddressingResolution) -> tuple[list[str], str]:
    participants = sorted(
        {
            item.strip()
            for item in (resolution.speaker_text, resolution.recipient_text)
            if item and item.strip()
        },
        key=str.casefold,
    )
    fingerprint = "|".join(item.casefold() for item in participants) or "unaddressed"
    return participants, fingerprint[:512]


async def associate_transmission(
    session: AsyncSession,
    *,
    transmission: Transmission,
    text: str,
    callsign_hint: str | None,
    operational_event: OperationalEvent | None,
    conversation_timeout_seconds: int,
    emergency_terms: set[str],
) -> tuple[RadioConversation, AddressingResolution]:
    """Resolve recipient/speaker and reuse only an active, matching conversation."""

    callsigns = await _callsign_candidates(
        session,
        organization_id=transmission.organization_id,
        site_id=transmission.site_id,
    )
    resolution = parse_radio_addressing(
        text,
        callsigns=callsigns,
        agent_names=await _agent_names(session, transmission=transmission),
        callsign_hint=callsign_hint,
        emergency_terms=emergency_terms,
    )
    transmission.speaker_callsign_id = resolution.speaker_callsign_id
    transmission.recipient_callsign_id = resolution.recipient_callsign_id
    transmission.speaker_text = resolution.speaker_text
    transmission.recipient_text = resolution.recipient_text
    transmission.addressed_to_agent = resolution.addressed_to_agent
    transmission.addressing_confidence = resolution.confidence

    participants, fingerprint = _participant_identity(resolution)
    activity_at = transmission.received_at or datetime.now(UTC)
    cutoff = activity_at - timedelta(seconds=max(conversation_timeout_seconds, 30))
    query = select(RadioConversation).where(
        RadioConversation.organization_id == transmission.organization_id,
        RadioConversation.site_id == transmission.site_id,
        RadioConversation.status == "open",
        RadioConversation.participant_fingerprint == fingerprint,
        RadioConversation.last_activity_at >= cutoff,
    )
    if transmission.channel_id is None:
        query = query.where(RadioConversation.channel_id.is_(None))
    else:
        query = query.where(RadioConversation.channel_id == transmission.channel_id)
    conversation = await session.scalar(
        query.order_by(RadioConversation.last_activity_at.desc()).limit(1)
    )

    if conversation is None:
        conversation = RadioConversation(
            organization_id=transmission.organization_id,
            site_id=transmission.site_id,
            channel_id=transmission.channel_id,
            status="open",
            started_at=activity_at,
            last_activity_at=activity_at,
            primary_topic=operational_event.event_type if operational_event else None,
            active_location=operational_event.location_text if operational_event else None,
            operational_event_id=operational_event.id if operational_event else None,
            participants=participants,
            participant_fingerprint=fingerprint,
        )
        session.add(conversation)
        await session.flush()
    else:
        conversation.last_activity_at = activity_at
        if operational_event is not None:
            conversation.primary_topic = conversation.primary_topic or operational_event.event_type
            conversation.active_location = (
                operational_event.location_text or conversation.active_location
            )
            conversation.operational_event_id = (
                conversation.operational_event_id or operational_event.id
            )

    transmission.conversation_id = conversation.id
    await session.flush()
    return conversation, resolution
