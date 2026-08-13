"""Tenant-safe persistence and processing services for the radio intelligence pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable
from terrasatch.identity.models import Site, Team
from terrasatch.intelligence.core import TerraEngine
from terrasatch.organizations.service import slugify
from terrasatch.radio.models import Agent, Callsign, Channel, OperationalEvent, Transcript, Transmission
from terrasatch.radio.schemas import (
    AgentCreateRequest,
    CallsignCreateRequest,
    ChannelCreateRequest,
    TransmissionCreateRequest,
)


async def _site_for_org(session: AsyncSession, *, organization_id: UUID, site_id: UUID) -> Site:
    site = await session.scalar(
        select(Site).where(
            Site.id == site_id,
            Site.organization_id == organization_id,
            Site.enabled.is_(True),
        )
    )
    if site is None:
        raise InvalidConfiguration("Site was not found in the authenticated organization")
    return site


async def _agent_for_org(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
) -> Agent:
    agent = await session.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.organization_id == organization_id,
            Agent.enabled.is_(True),
        )
    )
    if agent is None:
        raise InvalidConfiguration("Agent was not found in the authenticated organization")
    return agent


async def _channel_for_org(
    session: AsyncSession,
    *,
    organization_id: UUID,
    channel_id: UUID,
) -> Channel:
    channel = await session.scalar(
        select(Channel).where(
            Channel.id == channel_id,
            Channel.organization_id == organization_id,
            Channel.enabled.is_(True),
        )
    )
    if channel is None:
        raise InvalidConfiguration("Channel was not found in the authenticated organization")
    return channel


async def create_agent(
    session: AsyncSession,
    *,
    organization_id: UUID,
    payload: AgentCreateRequest,
) -> Agent:
    await _site_for_org(session, organization_id=organization_id, site_id=payload.site_id)
    slug = slugify(payload.name)
    existing = await session.scalar(
        select(Agent).where(Agent.organization_id == organization_id, Agent.slug == slug)
    )
    if existing is not None:
        raise InvalidConfiguration(f"Agent slug '{slug}' already exists")
    agent = Agent(
        organization_id=organization_id,
        site_id=payload.site_id,
        name=payload.name.strip(),
        slug=slug,
        profile=payload.profile.strip(),
    )
    session.add(agent)
    await session.flush()
    return agent


async def list_agents(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> list[Agent]:
    return list(
        await session.scalars(
            select(Agent)
            .where(Agent.organization_id == organization_id)
            .order_by(Agent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


async def create_channel(
    session: AsyncSession,
    *,
    organization_id: UUID,
    payload: ChannelCreateRequest,
) -> Channel:
    await _site_for_org(session, organization_id=organization_id, site_id=payload.site_id)
    if payload.agent_id is not None:
        agent = await _agent_for_org(
            session,
            organization_id=organization_id,
            agent_id=payload.agent_id,
        )
        if agent.site_id != payload.site_id:
            raise InvalidConfiguration("Channel and agent must belong to the same site")
    slug = slugify(payload.name)
    existing = await session.scalar(
        select(Channel).where(Channel.organization_id == organization_id, Channel.slug == slug)
    )
    if existing is not None:
        raise InvalidConfiguration(f"Channel slug '{slug}' already exists")
    channel = Channel(
        organization_id=organization_id,
        site_id=payload.site_id,
        agent_id=payload.agent_id,
        name=payload.name.strip(),
        slug=slug,
        profile=payload.profile.strip(),
    )
    session.add(channel)
    await session.flush()
    return channel


async def list_channels(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> list[Channel]:
    return list(
        await session.scalars(
            select(Channel)
            .where(Channel.organization_id == organization_id)
            .order_by(Channel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


async def create_callsign(
    session: AsyncSession,
    *,
    organization_id: UUID,
    payload: CallsignCreateRequest,
) -> Callsign:
    if payload.site_id is not None:
        await _site_for_org(session, organization_id=organization_id, site_id=payload.site_id)
    if payload.team_id is not None:
        team = await session.scalar(
            select(Team).where(
                Team.id == payload.team_id,
                Team.organization_id == organization_id,
                Team.enabled.is_(True),
            )
        )
        if team is None:
            raise InvalidConfiguration("Team was not found in the authenticated organization")
    existing = await session.scalar(
        select(Callsign).where(
            Callsign.organization_id == organization_id,
            Callsign.name == payload.name.strip(),
        )
    )
    if existing is not None:
        raise InvalidConfiguration(f"Callsign '{payload.name.strip()}' already exists")
    aliases = sorted({alias.strip() for alias in payload.aliases if alias.strip()})
    callsign = Callsign(
        organization_id=organization_id,
        site_id=payload.site_id,
        team_id=payload.team_id,
        name=payload.name.strip(),
        aliases=aliases,
    )
    session.add(callsign)
    await session.flush()
    return callsign


async def list_callsigns(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> list[Callsign]:
    return list(
        await session.scalars(
            select(Callsign)
            .where(Callsign.organization_id == organization_id)
            .order_by(Callsign.name)
            .limit(limit)
            .offset(offset)
        )
    )


async def _existing_ingest(
    session: AsyncSession,
    *,
    organization_id: UUID,
    source_message_id: str,
) -> tuple[Transmission, Transcript, list[OperationalEvent]] | None:
    transmission = await session.scalar(
        select(Transmission).where(
            Transmission.organization_id == organization_id,
            Transmission.source_message_id == source_message_id,
        )
    )
    if transmission is None:
        return None
    transcript = await session.scalar(
        select(Transcript).where(
            Transcript.organization_id == organization_id,
            Transcript.transmission_id == transmission.id,
        )
    )
    if transcript is None:
        raise InvalidConfiguration("Existing transmission is missing its transcript")
    events = list(
        await session.scalars(
            select(OperationalEvent)
            .where(
                OperationalEvent.organization_id == organization_id,
                OperationalEvent.transmission_id == transmission.id,
            )
            .order_by(OperationalEvent.created_at)
        )
    )
    return transmission, transcript, events


async def ingest_transmission(
    session: AsyncSession,
    *,
    settings: Settings,
    organization_id: UUID,
    payload: TransmissionCreateRequest,
) -> tuple[Transmission, Transcript, list[OperationalEvent], bool]:
    """Persist source + transcript + structured events in one transaction.

    Repeated ``source_message_id`` values for the same tenant return the previously persisted
    records rather than generating duplicates.
    """

    source_message_id = payload.source_message_id.strip()
    existing = await _existing_ingest(
        session,
        organization_id=organization_id,
        source_message_id=source_message_id,
    )
    if existing is not None:
        transmission, transcript, events = existing
        return transmission, transcript, events, True

    await _site_for_org(session, organization_id=organization_id, site_id=payload.site_id)
    agent: Agent | None = None
    channel: Channel | None = None
    if payload.agent_id is not None:
        agent = await _agent_for_org(
            session,
            organization_id=organization_id,
            agent_id=payload.agent_id,
        )
        if agent.site_id != payload.site_id:
            raise InvalidConfiguration("Transmission site does not match the selected agent")
    if payload.channel_id is not None:
        channel = await _channel_for_org(
            session,
            organization_id=organization_id,
            channel_id=payload.channel_id,
        )
        if channel.site_id != payload.site_id:
            raise InvalidConfiguration("Transmission site does not match the selected channel")
        if agent is not None and channel.agent_id not in {None, agent.id}:
            raise InvalidConfiguration("Transmission channel is assigned to a different agent")

    raw_text = payload.text.strip()
    normalized_text = " ".join(raw_text.split())
    transmission = Transmission(
        organization_id=organization_id,
        site_id=payload.site_id,
        agent_id=payload.agent_id,
        channel_id=payload.channel_id,
        source_type=payload.source.strip(),
        source_message_id=source_message_id,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        received_at=datetime.now(UTC),
    )
    session.add(transmission)
    await session.flush()

    started = perf_counter()
    transcript = Transcript(
        organization_id=organization_id,
        transmission_id=transmission.id,
        raw_text=raw_text,
        normalized_text=normalized_text,
        language="en",
        confidence=1.0,
        provider="submitted_text",
        model=None,
    )
    session.add(transcript)
    await session.flush()

    if settings.intelligence_provider != "deterministic":
        raise ProviderUnavailable(
            f"Intelligence provider '{settings.intelligence_provider}' is not implemented yet"
        )
    engine = TerraEngine()
    extracted = await engine.process(text=normalized_text, callsign_hint=payload.callsign)
    transcript.processing_latency_ms = max(int((perf_counter() - started) * 1000), 0)

    events: list[OperationalEvent] = []
    for item in extracted:
        event = OperationalEvent(
            organization_id=organization_id,
            site_id=payload.site_id,
            transmission_id=transmission.id,
            transcript_id=transcript.id,
            event_type=item.event_type.value,
            summary=item.summary,
            callsign=item.callsign,
            location_text=item.location_text,
            latitude=item.latitude,
            longitude=item.longitude,
            elevation_ft=item.elevation_ft,
            aspect=item.aspect,
            severity=item.severity,
            confidence=item.confidence,
            data=item.data,
            source=payload.source.strip(),
        )
        session.add(event)
        events.append(event)
    await session.flush()
    return transmission, transcript, events, False


async def list_transmissions(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> list[Transmission]:
    return list(
        await session.scalars(
            select(Transmission)
            .where(Transmission.organization_id == organization_id)
            .order_by(Transmission.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


async def get_transmission(
    session: AsyncSession,
    *,
    organization_id: UUID,
    transmission_id: UUID,
) -> Transmission:
    transmission = await session.scalar(
        select(Transmission).where(
            Transmission.id == transmission_id,
            Transmission.organization_id == organization_id,
        )
    )
    if transmission is None:
        raise InvalidConfiguration("Transmission was not found")
    return transmission


async def list_transcripts(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> list[Transcript]:
    return list(
        await session.scalars(
            select(Transcript)
            .where(Transcript.organization_id == organization_id)
            .order_by(Transcript.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


async def get_transcript(
    session: AsyncSession,
    *,
    organization_id: UUID,
    transcript_id: UUID,
) -> Transcript:
    transcript = await session.scalar(
        select(Transcript).where(
            Transcript.id == transcript_id,
            Transcript.organization_id == organization_id,
        )
    )
    if transcript is None:
        raise InvalidConfiguration("Transcript was not found")
    return transcript


async def list_events(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> list[OperationalEvent]:
    return list(
        await session.scalars(
            select(OperationalEvent)
            .where(OperationalEvent.organization_id == organization_id)
            .order_by(OperationalEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


async def get_event(
    session: AsyncSession,
    *,
    organization_id: UUID,
    event_id: UUID,
) -> OperationalEvent:
    event = await session.scalar(
        select(OperationalEvent).where(
            OperationalEvent.id == event_id,
            OperationalEvent.organization_id == organization_id,
        )
    )
    if event is None:
        raise InvalidConfiguration("Operational event was not found")
    return event
