"""Tenant-safe REST resources for the TerraSatch radio intelligence vertical slice."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.auth.dependencies import Principal, require_any_scope, require_scope
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.events.bus import publish_event
from terrasatch.radio.activation_service import validate_edge_ingest_activation
from terrasatch.radio.models import Agent, Callsign, Channel, OperationalEvent, Transcript, Transmission
from terrasatch.radio.schemas import (
    AgentCreateRequest,
    AgentResponse,
    AgentUpdateRequest,
    CallsignCreateRequest,
    CallsignResponse,
    CallsignUpdateRequest,
    ChannelCreateRequest,
    ChannelResponse,
    ChannelUpdateRequest,
    OperationalEventResponse,
    PaginatedAgents,
    PaginatedCallsigns,
    PaginatedChannels,
    PaginatedEvents,
    PaginatedTranscripts,
    PaginatedTransmissions,
    TranscriptResponse,
    TransmissionCreateRequest,
    TransmissionIngestResponse,
    TransmissionResponse,
)
from terrasatch.radio.service import (
    create_agent,
    create_callsign,
    create_channel,
    get_agent,
    get_callsign,
    get_channel,
    get_event,
    get_transcript,
    get_transmission,
    ingest_transmission,
    list_agents,
    list_callsigns,
    list_channels,
    list_events,
    list_transcripts,
    list_transmissions,
    update_agent,
    update_callsign,
    update_channel,
)

router = APIRouter(tags=["radio-intelligence"])
logger = structlog.get_logger(__name__)


async def _run_database[Result](
    settings: Settings,
    operation: Callable[[AsyncSession], Awaitable[Result]],
) -> Result:
    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        try:
            result = await operation(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


def _agent_response(item: Agent) -> AgentResponse:
    return AgentResponse(
        id=item.id,
        organization_id=item.organization_id,
        site_id=item.site_id,
        name=item.name,
        slug=item.slug,
        profile=item.profile,
        enabled=item.enabled,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _channel_response(item: Channel) -> ChannelResponse:
    return ChannelResponse(
        id=item.id,
        organization_id=item.organization_id,
        site_id=item.site_id,
        agent_id=item.agent_id,
        name=item.name,
        slug=item.slug,
        profile=item.profile,
        enabled=item.enabled,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _callsign_response(item: Callsign) -> CallsignResponse:
    return CallsignResponse(
        id=item.id,
        organization_id=item.organization_id,
        site_id=item.site_id,
        team_id=item.team_id,
        name=item.name,
        aliases=item.aliases,
        enabled=item.enabled,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _transmission_response(item: Transmission) -> TransmissionResponse:
    return TransmissionResponse(
        id=item.id,
        organization_id=item.organization_id,
        site_id=item.site_id,
        agent_id=item.agent_id,
        channel_id=item.channel_id,
        source_type=item.source_type,
        source_message_id=item.source_message_id,
        started_at=item.started_at,
        ended_at=item.ended_at,
        received_at=item.received_at,
        created_at=item.created_at,
    )


def _transcript_response(item: Transcript) -> TranscriptResponse:
    return TranscriptResponse(
        id=item.id,
        organization_id=item.organization_id,
        transmission_id=item.transmission_id,
        raw_text=item.raw_text,
        normalized_text=item.normalized_text,
        language=item.language,
        confidence=item.confidence,
        provider=item.provider,
        model=item.model,
        processing_latency_ms=item.processing_latency_ms,
        created_at=item.created_at,
    )


def _event_response(item: OperationalEvent) -> OperationalEventResponse:
    return OperationalEventResponse(
        id=item.id,
        organization_id=item.organization_id,
        site_id=item.site_id,
        transmission_id=item.transmission_id,
        transcript_id=item.transcript_id,
        event_type=item.event_type,
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
        source=item.source,
        created_at=item.created_at,
    )


@router.get("/agents", response_model=PaginatedAgents)
async def get_agents(
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("read:agents", "read:events")),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    site_id: Annotated[UUID | None, Query()] = None,
    profile: Annotated[str | None, Query(max_length=100)] = None,
    enabled: Annotated[bool | None, Query()] = None,
) -> PaginatedAgents:
    items = await _run_database(
        request.app.state.settings,
        lambda session: list_agents(
            session,
            organization_id=principal.organization_id,
            limit=limit,
            offset=offset,
            site_id=site_id,
            profile=profile,
            enabled=enabled,
        ),
    )
    return PaginatedAgents(items=[_agent_response(item) for item in items], limit=limit, offset=offset)


@router.post("/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def post_agent(
    payload: AgentCreateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:agents"))],
) -> AgentResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: create_agent(
            session,
            organization_id=principal.organization_id,
            payload=payload,
        ),
    )
    return _agent_response(item)


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent_by_id(
    agent_id: UUID,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("read:agents", "read:events")),
    ],
) -> AgentResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: get_agent(
            session,
            organization_id=principal.organization_id,
            agent_id=agent_id,
        ),
    )
    return _agent_response(item)


@router.patch("/agents/{agent_id}", response_model=AgentResponse)
async def patch_agent(
    agent_id: UUID,
    payload: AgentUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:agents"))],
) -> AgentResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: update_agent(
            session,
            organization_id=principal.organization_id,
            agent_id=agent_id,
            payload=payload,
        ),
    )
    return _agent_response(item)


@router.get("/channels", response_model=PaginatedChannels)
async def get_channels(
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("read:channels", "read:events")),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    site_id: Annotated[UUID | None, Query()] = None,
    agent_id: Annotated[UUID | None, Query()] = None,
    profile: Annotated[str | None, Query(max_length=100)] = None,
    enabled: Annotated[bool | None, Query()] = None,
) -> PaginatedChannels:
    items = await _run_database(
        request.app.state.settings,
        lambda session: list_channels(
            session,
            organization_id=principal.organization_id,
            limit=limit,
            offset=offset,
            site_id=site_id,
            agent_id=agent_id,
            profile=profile,
            enabled=enabled,
        ),
    )
    return PaginatedChannels(items=[_channel_response(item) for item in items], limit=limit, offset=offset)


@router.post("/channels", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def post_channel(
    payload: ChannelCreateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:channels"))],
) -> ChannelResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: create_channel(
            session,
            organization_id=principal.organization_id,
            payload=payload,
        ),
    )
    return _channel_response(item)


@router.get("/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel_by_id(
    channel_id: UUID,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("read:channels", "read:events")),
    ],
) -> ChannelResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: get_channel(
            session,
            organization_id=principal.organization_id,
            channel_id=channel_id,
        ),
    )
    return _channel_response(item)


@router.patch("/channels/{channel_id}", response_model=ChannelResponse)
async def patch_channel(
    channel_id: UUID,
    payload: ChannelUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:channels"))],
) -> ChannelResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: update_channel(
            session,
            organization_id=principal.organization_id,
            channel_id=channel_id,
            payload=payload,
        ),
    )
    return _channel_response(item)


@router.get("/callsigns", response_model=PaginatedCallsigns)
async def get_callsigns(
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("read:callsigns", "read:events")),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    site_id: Annotated[UUID | None, Query()] = None,
    team_id: Annotated[UUID | None, Query()] = None,
    enabled: Annotated[bool | None, Query()] = None,
) -> PaginatedCallsigns:
    items = await _run_database(
        request.app.state.settings,
        lambda session: list_callsigns(
            session,
            organization_id=principal.organization_id,
            limit=limit,
            offset=offset,
            site_id=site_id,
            team_id=team_id,
            enabled=enabled,
        ),
    )
    return PaginatedCallsigns(
        items=[_callsign_response(item) for item in items], limit=limit, offset=offset
    )


@router.post("/callsigns", response_model=CallsignResponse, status_code=status.HTTP_201_CREATED)
async def post_callsign(
    payload: CallsignCreateRequest,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("write:callsigns", "write:agents")),
    ],
) -> CallsignResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: create_callsign(
            session,
            organization_id=principal.organization_id,
            payload=payload,
        ),
    )
    return _callsign_response(item)


@router.get("/callsigns/{callsign_id}", response_model=CallsignResponse)
async def get_callsign_by_id(
    callsign_id: UUID,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("read:callsigns", "read:events")),
    ],
) -> CallsignResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: get_callsign(
            session,
            organization_id=principal.organization_id,
            callsign_id=callsign_id,
        ),
    )
    return _callsign_response(item)


@router.patch("/callsigns/{callsign_id}", response_model=CallsignResponse)
async def patch_callsign(
    callsign_id: UUID,
    payload: CallsignUpdateRequest,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("write:callsigns", "write:agents")),
    ],
) -> CallsignResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: update_callsign(
            session,
            organization_id=principal.organization_id,
            callsign_id=callsign_id,
            payload=payload,
        ),
    )
    return _callsign_response(item)


@router.post(
    "/transmissions",
    response_model=TransmissionIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_transmission(
    payload: TransmissionCreateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("edge:ingest"))],
) -> TransmissionIngestResponse:
    settings: Settings = request.app.state.settings
    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        try:
            await validate_edge_ingest_activation(
                session,
                organization_id=principal.organization_id,
                api_key_id=principal.api_key_id,
                payload=payload,
            )
            transmission, transcript, events, duplicate = await ingest_transmission(
                session,
                settings=settings,
                organization_id=principal.organization_id,
                payload=payload,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    transmission_response = _transmission_response(transmission)
    transcript_response = _transcript_response(transcript)
    event_responses = [_event_response(item) for item in events]

    if not duplicate:
        messages: list[tuple[str, str, dict[str, object]]] = [
            (
                "transmissions",
                "radio.transmission.created",
                transmission_response.model_dump(mode="json"),
            ),
            (
                "transcripts",
                "transcript.created",
                transcript_response.model_dump(mode="json"),
            ),
        ]
        messages.extend(
            ("events", "event.created", event.model_dump(mode="json")) for event in event_responses
        )
        for topic, event_type, event_payload in messages:
            try:
                await publish_event(
                    settings,
                    organization_id=principal.organization_id,
                    topic=topic,
                    event_type=event_type,
                    payload=event_payload,
                )
            except Exception as error:
                logger.warning(
                    "event_bus.publish_failed",
                    event_type=event_type,
                    error_type=type(error).__name__,
                )

    return TransmissionIngestResponse(
        transmission=transmission_response,
        transcript=transcript_response,
        events=event_responses,
        duplicate=duplicate,
    )


@router.get("/transmissions", response_model=PaginatedTransmissions)
async def get_transmissions(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:transmissions"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    site_id: Annotated[UUID | None, Query()] = None,
    agent_id: Annotated[UUID | None, Query()] = None,
    channel_id: Annotated[UUID | None, Query()] = None,
    source: Annotated[str | None, Query(max_length=64)] = None,
) -> PaginatedTransmissions:
    items = await _run_database(
        request.app.state.settings,
        lambda session: list_transmissions(
            session,
            organization_id=principal.organization_id,
            limit=limit,
            offset=offset,
            site_id=site_id,
            agent_id=agent_id,
            channel_id=channel_id,
            source=source,
        ),
    )
    return PaginatedTransmissions(
        items=[_transmission_response(item) for item in items], limit=limit, offset=offset
    )


@router.get("/transmissions/{transmission_id}", response_model=TransmissionResponse)
async def get_transmission_by_id(
    transmission_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:transmissions"))],
) -> TransmissionResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: get_transmission(
            session,
            organization_id=principal.organization_id,
            transmission_id=transmission_id,
        ),
    )
    return _transmission_response(item)


@router.get("/transcripts", response_model=PaginatedTranscripts)
async def get_transcripts(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:transcripts"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    transmission_id: Annotated[UUID | None, Query()] = None,
) -> PaginatedTranscripts:
    items = await _run_database(
        request.app.state.settings,
        lambda session: list_transcripts(
            session,
            organization_id=principal.organization_id,
            limit=limit,
            offset=offset,
            transmission_id=transmission_id,
        ),
    )
    return PaginatedTranscripts(
        items=[_transcript_response(item) for item in items], limit=limit, offset=offset
    )


@router.get("/transcripts/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript_by_id(
    transcript_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:transcripts"))],
) -> TranscriptResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: get_transcript(
            session,
            organization_id=principal.organization_id,
            transcript_id=transcript_id,
        ),
    )
    return _transcript_response(item)


@router.get("/events", response_model=PaginatedEvents)
async def get_operational_events(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:events"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    site_id: Annotated[UUID | None, Query()] = None,
    transmission_id: Annotated[UUID | None, Query()] = None,
    event_type: Annotated[str | None, Query(max_length=64)] = None,
    callsign: Annotated[str | None, Query(max_length=255)] = None,
) -> PaginatedEvents:
    items = await _run_database(
        request.app.state.settings,
        lambda session: list_events(
            session,
            organization_id=principal.organization_id,
            limit=limit,
            offset=offset,
            site_id=site_id,
            transmission_id=transmission_id,
            event_type=event_type,
            callsign=callsign,
        ),
    )
    return PaginatedEvents(items=[_event_response(item) for item in items], limit=limit, offset=offset)


@router.get("/events/{event_id}", response_model=OperationalEventResponse)
async def get_operational_event_by_id(
    event_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:events"))],
) -> OperationalEventResponse:
    item = await _run_database(
        request.app.state.settings,
        lambda session: get_event(
            session,
            organization_id=principal.organization_id,
            event_id=event_id,
        ),
    )
    return _event_response(item)
