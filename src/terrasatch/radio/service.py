"""Tenant-safe persistence and processing services for the radio intelligence pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.actions.evaluation import process_transmission_control_plane
from terrasatch.config import Settings
from terrasatch.errors import (
    InvalidConfiguration,
    ProviderUnavailable,
    ResourceConflict,
    ResourceNotFound,
)
from terrasatch.identity.models import Site, Team
from terrasatch.intelligence.core import TerraEngine
from terrasatch.intelligence.providers import (
    IntelligenceProviderError,
    IntelligenceSettings,
    build_intelligence_provider,
)
from terrasatch.organizations.service import slugify
from terrasatch.radio.models import (
    Agent,
    Callsign,
    Channel,
    OperationalEvent,
    Transcript,
    Transmission,
)
from terrasatch.radio.schemas import (
    AgentCreateRequest,
    AgentUpdateRequest,
    CallsignCreateRequest,
    CallsignUpdateRequest,
    ChannelCreateRequest,
    ChannelUpdateRequest,
    TransmissionCreateRequest,
)


async def _site_for_org(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
) -> Site:
    site = await session.scalar(
        select(Site).where(
            Site.id == site_id,
            Site.organization_id == organization_id,
            Site.enabled.is_(True),
        )
    )
    if site is None:
        raise ResourceNotFound("Site was not found in the authenticated organization")
    return site


async def _team_for_org(
    session: AsyncSession,
    *,
    organization_id: UUID,
    team_id: UUID,
) -> Team:
    team = await session.scalar(
        select(Team).where(
            Team.id == team_id,
            Team.organization_id == organization_id,
            Team.enabled.is_(True),
        )
    )
    if team is None:
        raise ResourceNotFound("Team was not found in the authenticated organization")
    return team


async def _agent_for_org(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    enabled_only: bool = True,
) -> Agent:
    query = select(Agent).where(
        Agent.id == agent_id,
        Agent.organization_id == organization_id,
    )
    if enabled_only:
        query = query.where(Agent.enabled.is_(True))
    agent = await session.scalar(query)
    if agent is None:
        raise ResourceNotFound("Agent was not found in the authenticated organization")
    return agent


async def _channel_for_org(
    session: AsyncSession,
    *,
    organization_id: UUID,
    channel_id: UUID,
    enabled_only: bool = True,
) -> Channel:
    query = select(Channel).where(
        Channel.id == channel_id,
        Channel.organization_id == organization_id,
    )
    if enabled_only:
        query = query.where(Channel.enabled.is_(True))
    channel = await session.scalar(query)
    if channel is None:
        raise ResourceNotFound("Channel was not found in the authenticated organization")
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
        raise ResourceConflict(f"Agent slug '{slug}' already exists")
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
    site_id: UUID | None = None,
    profile: str | None = None,
    enabled: bool | None = None,
) -> list[Agent]:
    query = select(Agent).where(Agent.organization_id == organization_id)
    if site_id is not None:
        query = query.where(Agent.site_id == site_id)
    if profile is not None:
        query = query.where(Agent.profile == profile)
    if enabled is not None:
        query = query.where(Agent.enabled.is_(enabled))
    return list(
        await session.scalars(
            query.order_by(Agent.created_at.desc()).limit(limit).offset(offset)
        )
    )


async def get_agent(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
) -> Agent:
    return await _agent_for_org(
        session,
        organization_id=organization_id,
        agent_id=agent_id,
        enabled_only=False,
    )


async def update_agent(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    payload: AgentUpdateRequest,
) -> Agent:
    agent = await get_agent(session, organization_id=organization_id, agent_id=agent_id)
    if payload.name is not None:
        name = payload.name.strip()
        slug = slugify(name)
        existing = await session.scalar(
            select(Agent).where(
                Agent.organization_id == organization_id,
                Agent.slug == slug,
                Agent.id != agent.id,
            )
        )
        if existing is not None:
            raise ResourceConflict(f"Agent slug '{slug}' already exists")
        agent.name = name
        agent.slug = slug
    if payload.profile is not None:
        agent.profile = payload.profile.strip()
    if payload.enabled is not None:
        agent.enabled = payload.enabled
    await session.flush()
    return agent


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
        raise ResourceConflict(f"Channel slug '{slug}' already exists")
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
    site_id: UUID | None = None,
    agent_id: UUID | None = None,
    profile: str | None = None,
    enabled: bool | None = None,
) -> list[Channel]:
    query = select(Channel).where(Channel.organization_id == organization_id)
    if site_id is not None:
        query = query.where(Channel.site_id == site_id)
    if agent_id is not None:
        query = query.where(Channel.agent_id == agent_id)
    if profile is not None:
        query = query.where(Channel.profile == profile)
    if enabled is not None:
        query = query.where(Channel.enabled.is_(enabled))
    return list(
        await session.scalars(
            query.order_by(Channel.created_at.desc()).limit(limit).offset(offset)
        )
    )


async def get_channel(
    session: AsyncSession,
    *,
    organization_id: UUID,
    channel_id: UUID,
) -> Channel:
    return await _channel_for_org(
        session,
        organization_id=organization_id,
        channel_id=channel_id,
        enabled_only=False,
    )


async def update_channel(
    session: AsyncSession,
    *,
    organization_id: UUID,
    channel_id: UUID,
    payload: ChannelUpdateRequest,
) -> Channel:
    channel = await get_channel(
        session,
        organization_id=organization_id,
        channel_id=channel_id,
    )
    if payload.name is not None:
        name = payload.name.strip()
        slug = slugify(name)
        existing = await session.scalar(
            select(Channel).where(
                Channel.organization_id == organization_id,
                Channel.slug == slug,
                Channel.id != channel.id,
            )
        )
        if existing is not None:
            raise ResourceConflict(f"Channel slug '{slug}' already exists")
        channel.name = name
        channel.slug = slug
    if "agent_id" in payload.model_fields_set:
        if payload.agent_id is not None:
            agent = await _agent_for_org(
                session,
                organization_id=organization_id,
                agent_id=payload.agent_id,
            )
            if agent.site_id != channel.site_id:
                raise InvalidConfiguration("Channel and agent must belong to the same site")
        channel.agent_id = payload.agent_id
    if payload.profile is not None:
        channel.profile = payload.profile.strip()
    if payload.enabled is not None:
        channel.enabled = payload.enabled
    await session.flush()
    return channel


async def _validate_callsign_bindings(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID | None,
    team_id: UUID | None,
) -> None:
    if site_id is not None:
        await _site_for_org(session, organization_id=organization_id, site_id=site_id)
    if team_id is not None:
        team = await _team_for_org(
            session,
            organization_id=organization_id,
            team_id=team_id,
        )
        if site_id is not None and team.site_id is not None and team.site_id != site_id:
            raise InvalidConfiguration("Callsign site and team must reference the same site")


async def create_callsign(
    session: AsyncSession,
    *,
    organization_id: UUID,
    payload: CallsignCreateRequest,
) -> Callsign:
    await _validate_callsign_bindings(
        session,
        organization_id=organization_id,
        site_id=payload.site_id,
        team_id=payload.team_id,
    )
    name = payload.name.strip()
    existing = await session.scalar(
        select(Callsign).where(
            Callsign.organization_id == organization_id,
            Callsign.name == name,
        )
    )
    if existing is not None:
        raise ResourceConflict(f"Callsign '{name}' already exists")
    aliases = sorted({alias.strip() for alias in payload.aliases if alias.strip()})
    callsign = Callsign(
        organization_id=organization_id,
        site_id=payload.site_id,
        team_id=payload.team_id,
        name=name,
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
    site_id: UUID | None = None,
    team_id: UUID | None = None,
    enabled: bool | None = None,
) -> list[Callsign]:
    query = select(Callsign).where(Callsign.organization_id == organization_id)
    if site_id is not None:
        query = query.where(Callsign.site_id == site_id)
    if team_id is not None:
        query = query.where(Callsign.team_id == team_id)
    if enabled is not None:
        query = query.where(Callsign.enabled.is_(enabled))
    return list(
        await session.scalars(query.order_by(Callsign.name).limit(limit).offset(offset))
    )


async def get_callsign(
    session: AsyncSession,
    *,
    organization_id: UUID,
    callsign_id: UUID,
) -> Callsign:
    callsign = await session.scalar(
        select(Callsign).where(
            Callsign.id == callsign_id,
            Callsign.organization_id == organization_id,
        )
    )
    if callsign is None:
        raise ResourceNotFound("Callsign was not found in the authenticated organization")
    return callsign


async def update_callsign(
    session: AsyncSession,
    *,
    organization_id: UUID,
    callsign_id: UUID,
    payload: CallsignUpdateRequest,
) -> Callsign:
    callsign = await get_callsign(
        session,
        organization_id=organization_id,
        callsign_id=callsign_id,
    )
    site_id = payload.site_id if "site_id" in payload.model_fields_set else callsign.site_id
    team_id = payload.team_id if "team_id" in payload.model_fields_set else callsign.team_id
    await _validate_callsign_bindings(
        session,
        organization_id=organization_id,
        site_id=site_id,
        team_id=team_id,
    )
    if payload.name is not None:
        name = payload.name.strip()
        existing = await session.scalar(
            select(Callsign).where(
                Callsign.organization_id == organization_id,
                Callsign.name == name,
                Callsign.id != callsign.id,
            )
        )
        if existing is not None:
            raise ResourceConflict(f"Callsign '{name}' already exists")
        callsign.name = name
    if "site_id" in payload.model_fields_set:
        callsign.site_id = payload.site_id
    if "team_id" in payload.model_fields_set:
        callsign.team_id = payload.team_id
    if payload.aliases is not None:
        callsign.aliases = sorted({alias.strip() for alias in payload.aliases if alias.strip()})
    if payload.enabled is not None:
        callsign.enabled = payload.enabled
    await session.flush()
    return callsign


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
    records rather than generating duplicates. A savepoint also converts a concurrent duplicate
    insert race into the same idempotent response without invalidating the outer
    request transaction.
    """

    source_message_id = payload.source_message_id.strip()
    existing = await _existing_ingest(
        session,
        organization_id=organization_id,
        source_message_id=source_message_id,
    )
    if existing is not None:
        transmission, transcript, existing_events = existing
        return transmission, transcript, existing_events, True

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
        rf_metadata=payload.rf_metadata.model_dump(mode="json", exclude_none=False),
    )

    try:
        async with session.begin_nested():
            session.add(transmission)
            await session.flush()
    except IntegrityError:
        raced = await _existing_ingest(
            session,
            organization_id=organization_id,
            source_message_id=source_message_id,
        )
        if raced is None:
            raise
        raced_transmission, raced_transcript, raced_events = raced
        return raced_transmission, raced_transcript, raced_events, True

    started = perf_counter()
    transcript = Transcript(
        organization_id=organization_id,
        transmission_id=transmission.id,
        raw_text=raw_text,
        normalized_text=normalized_text,
        language=payload.transcript_language or "en",
        confidence=(
            payload.transcript_confidence if payload.transcript_confidence is not None else 1.0
        ),
        provider=payload.transcript_provider or "submitted_text",
        model=payload.transcript_model,
    )
    session.add(transcript)
    await session.flush()

    try:
        provider = build_intelligence_provider(cast(IntelligenceSettings, settings))
    except IntelligenceProviderError as exc:
        raise ProviderUnavailable(str(exc)) from exc
    engine = TerraEngine(provider)
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
    await process_transmission_control_plane(
        session,
        transmission=transmission,
        text=normalized_text,
        callsign_hint=payload.callsign,
        operational_event=events[0] if events else None,
    )
    return transmission, transcript, events, False


async def list_transmissions(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
    site_id: UUID | None = None,
    agent_id: UUID | None = None,
    channel_id: UUID | None = None,
    source: str | None = None,
) -> list[Transmission]:
    query = select(Transmission).where(Transmission.organization_id == organization_id)
    if site_id is not None:
        query = query.where(Transmission.site_id == site_id)
    if agent_id is not None:
        query = query.where(Transmission.agent_id == agent_id)
    if channel_id is not None:
        query = query.where(Transmission.channel_id == channel_id)
    if source is not None:
        query = query.where(Transmission.source_type == source)
    return list(
        await session.scalars(
            query.order_by(Transmission.created_at.desc()).limit(limit).offset(offset)
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
        raise ResourceNotFound("Transmission was not found")
    return transmission


async def list_transcripts(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
    transmission_id: UUID | None = None,
) -> list[Transcript]:
    query = select(Transcript).where(Transcript.organization_id == organization_id)
    if transmission_id is not None:
        query = query.where(Transcript.transmission_id == transmission_id)
    return list(
        await session.scalars(
            query.order_by(Transcript.created_at.desc()).limit(limit).offset(offset)
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
        raise ResourceNotFound("Transcript was not found")
    return transcript


async def list_events(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
    site_id: UUID | None = None,
    transmission_id: UUID | None = None,
    event_type: str | None = None,
    callsign: str | None = None,
) -> list[OperationalEvent]:
    query = select(OperationalEvent).where(OperationalEvent.organization_id == organization_id)
    if site_id is not None:
        query = query.where(OperationalEvent.site_id == site_id)
    if transmission_id is not None:
        query = query.where(OperationalEvent.transmission_id == transmission_id)
    if event_type is not None:
        query = query.where(OperationalEvent.event_type == event_type)
    if callsign is not None:
        query = query.where(OperationalEvent.callsign == callsign)
    return list(
        await session.scalars(
            query.order_by(OperationalEvent.created_at.desc()).limit(limit).offset(offset)
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
        raise ResourceNotFound("Operational event was not found")
    return event
