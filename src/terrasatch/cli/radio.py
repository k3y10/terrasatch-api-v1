"""CLI operations for agents, channels, callsigns, events, and the software radio simulator."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID, uuid4

import typer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.errors import TerraSatchError
from terrasatch.events.bus import publish_event
from terrasatch.identity.models import Site
from terrasatch.organizations.service import resolve_organization
from terrasatch.radio.models import Agent, OperationalEvent
from terrasatch.radio.schemas import (
    AgentCreateRequest,
    CallsignCreateRequest,
    ChannelCreateRequest,
    TransmissionCreateRequest,
)
from terrasatch.radio.service import (
    create_agent,
    create_callsign,
    create_channel,
    get_event,
    ingest_transmission,
    list_agents,
    list_callsigns,
    list_channels,
    list_events,
)

agent_app = typer.Typer(help="Manage TerraSatch processing agents.", no_args_is_help=True)
channel_app = typer.Typer(help="Manage logical radio channels.", no_args_is_help=True)
callsign_app = typer.Typer(help="Manage radio callsigns.", no_args_is_help=True)
event_app = typer.Typer(help="Inspect structured operational events.", no_args_is_help=True)
simulate_app = typer.Typer(
    help="Run deterministic TerraSatch simulation inputs.", no_args_is_help=True
)


def register_radio_cli(root: typer.Typer) -> None:
    """Register radio-domain commands without modifying the existing admin command groups."""

    root.add_typer(agent_app, name="agent")
    root.add_typer(channel_app, name="channel")
    root.add_typer(callsign_app, name="callsign")
    root.add_typer(event_app, name="event")
    root.add_typer(simulate_app, name="simulate")


def _load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as error:
        typer.echo(f"Configuration invalid: {error.errors()[0]['msg']}", err=True)
        raise typer.Exit(code=1) from error


def _run_database[Result](
    operation: Callable[[AsyncSession, Settings], Awaitable[Result]],
) -> Result:
    async def run() -> Result:
        settings = _load_settings()
        session_factory = create_session_factory(settings)
        async with session_factory() as session:
            try:
                result = await operation(session, settings)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    try:
        return asyncio.run(run())
    except TerraSatchError as error:
        typer.echo(f"Error [{error.code}]: {error.message}", err=True)
        raise typer.Exit(code=1) from error


def _emit(data: object, *, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        typer.echo(str(data))


async def _resolve_site(
    session: AsyncSession,
    *,
    organization: str,
    site: str,
) -> tuple[UUID, Site]:
    selected_org = await resolve_organization(session, organization)
    try:
        site_id = UUID(site)
    except ValueError:
        query = select(Site).where(
            Site.organization_id == selected_org.id,
            Site.enabled.is_(True),
            (Site.slug == site) | (Site.name == site),
        )
    else:
        query = select(Site).where(
            Site.organization_id == selected_org.id,
            Site.enabled.is_(True),
            Site.id == site_id,
        )
    selected_site = await session.scalar(query)
    if selected_site is None:
        from terrasatch.errors import ResourceNotFound

        raise ResourceNotFound("Site was not found in the selected organization")
    return selected_org.id, selected_site


@agent_app.command("create")
def agent_create(
    name: str = typer.Option(..., "--name"),
    organization: str = typer.Option(..., "--organization"),
    site: str = typer.Option(..., "--site"),
    profile: str = typer.Option("general", "--profile"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Create a processing agent under one organization/site."""

    async def operation(session: AsyncSession, _settings: Settings):
        organization_id, selected_site = await _resolve_site(
            session, organization=organization, site=site
        )
        return await create_agent(
            session,
            organization_id=organization_id,
            payload=AgentCreateRequest(name=name, site_id=selected_site.id, profile=profile),
        )

    item = _run_database(operation)
    data = {
        "id": str(item.id),
        "organization_id": str(item.organization_id),
        "site_id": str(item.site_id),
        "name": item.name,
        "profile": item.profile,
        "enabled": item.enabled,
    }
    _emit(data if as_json else f"Created agent {item.name} ({item.id})", as_json=as_json)


@agent_app.command("list")
def agent_list(
    organization: str = typer.Option(..., "--organization"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List processing agents in one organization."""

    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        return await list_agents(session, organization_id=selected_org.id, limit=100, offset=0)

    items = _run_database(operation)
    data = [
        {
            "id": str(item.id),
            "site_id": str(item.site_id),
            "name": item.name,
            "profile": item.profile,
            "enabled": item.enabled,
        }
        for item in items
    ]
    _emit(
        data
        if as_json
        else (
            "No agents found."
            if not data
            else "\n".join(
                f"{row['id']}  {row['name']}  {row['profile']}  {'ON' if row['enabled'] else 'OFF'}"
                for row in data
            )
        ),
        as_json=as_json,
    )


@channel_app.command("create")
def channel_create(
    name: str = typer.Option(..., "--name"),
    organization: str = typer.Option(..., "--organization"),
    site: str = typer.Option(..., "--site"),
    agent_id: Annotated[UUID | None, typer.Option("--agent-id")] = None,
    profile: str = typer.Option("general", "--profile"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Create one logical monitored channel."""

    async def operation(session: AsyncSession, _settings: Settings):
        organization_id, selected_site = await _resolve_site(
            session, organization=organization, site=site
        )
        return await create_channel(
            session,
            organization_id=organization_id,
            payload=ChannelCreateRequest(
                name=name,
                site_id=selected_site.id,
                agent_id=agent_id,
                profile=profile,
            ),
        )

    item = _run_database(operation)
    data = {
        "id": str(item.id),
        "site_id": str(item.site_id),
        "agent_id": str(item.agent_id) if item.agent_id else None,
        "name": item.name,
        "profile": item.profile,
        "enabled": item.enabled,
    }
    _emit(data if as_json else f"Created channel {item.name} ({item.id})", as_json=as_json)


@channel_app.command("list")
def channel_list(
    organization: str = typer.Option(..., "--organization"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List logical channels in one organization."""

    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        return await list_channels(session, organization_id=selected_org.id, limit=100, offset=0)

    items = _run_database(operation)
    data = [
        {
            "id": str(item.id),
            "site_id": str(item.site_id),
            "name": item.name,
            "profile": item.profile,
            "enabled": item.enabled,
        }
        for item in items
    ]
    _emit(
        data
        if as_json
        else (
            "No channels found."
            if not data
            else "\n".join(
                f"{row['id']}  {row['name']}  {row['profile']}  {'ON' if row['enabled'] else 'OFF'}"
                for row in data
            )
        ),
        as_json=as_json,
    )


@callsign_app.command("add")
def callsign_add(
    name: str = typer.Option(..., "--name"),
    organization: str = typer.Option(..., "--organization"),
    site: str | None = typer.Option(None, "--site"),
    alias: Annotated[list[str] | None, typer.Option("--alias")] = None,
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Add a callsign and optional aliases."""

    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        site_id = None
        if site is not None:
            _, selected_site = await _resolve_site(session, organization=organization, site=site)
            site_id = selected_site.id
        return await create_callsign(
            session,
            organization_id=selected_org.id,
            payload=CallsignCreateRequest(name=name, site_id=site_id, aliases=alias or []),
        )

    item = _run_database(operation)
    data = {"id": str(item.id), "name": item.name, "aliases": item.aliases, "enabled": item.enabled}
    _emit(data if as_json else f"Added callsign {item.name} ({item.id})", as_json=as_json)


@callsign_app.command("list")
def callsign_list(
    organization: str = typer.Option(..., "--organization"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List configured callsigns."""

    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        return await list_callsigns(session, organization_id=selected_org.id, limit=100, offset=0)

    items = _run_database(operation)
    data = [
        {"id": str(item.id), "name": item.name, "aliases": item.aliases, "enabled": item.enabled}
        for item in items
    ]
    _emit(
        data
        if as_json
        else (
            "No callsigns found."
            if not data
            else "\n".join(
                f"{row['id']}  {row['name']}  {'ON' if row['enabled'] else 'OFF'}" for row in data
            )
        ),
        as_json=as_json,
    )


def _event_data(item: OperationalEvent) -> dict[str, object]:
    return {
        "id": str(item.id),
        "event_type": item.event_type,
        "summary": item.summary,
        "callsign": item.callsign,
        "location_text": item.location_text,
        "aspect": item.aspect,
        "elevation_ft": item.elevation_ft,
        "severity": item.severity,
        "confidence": item.confidence,
        "transmission_id": str(item.transmission_id),
        "transcript_id": str(item.transcript_id),
        "created_at": item.created_at,
    }


@event_app.command("list")
def event_list(
    organization: str = typer.Option(..., "--organization"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List persisted structured operational events."""

    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        return await list_events(session, organization_id=selected_org.id, limit=100, offset=0)

    items: list[OperationalEvent] = _run_database(operation)
    data = [_event_data(item) for item in items]
    _emit(
        data
        if as_json
        else (
            "No events found."
            if not data
            else "\n".join(
                f"{row['id']}  {row['event_type']:<18} {row['summary']}" for row in data
            )
        ),
        as_json=as_json,
    )


@event_app.command("show")
def event_show(
    event_id: Annotated[UUID, typer.Argument(help="Operational event UUID.")],
    organization: str = typer.Option(..., "--organization"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one persisted structured event with its source references."""

    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        return await get_event(
            session,
            organization_id=selected_org.id,
            event_id=event_id,
        )

    item = _run_database(operation)
    data = _event_data(item)
    if as_json:
        _emit(data, as_json=True)
        return
    typer.echo(f"{data['event_type']}  {data['summary']}")
    typer.echo(f"Event:        {data['id']}")
    typer.echo(f"Transmission: {data['transmission_id']}")
    typer.echo(f"Transcript:   {data['transcript_id']}")


async def _publish_simulated_records(
    settings: Settings,
    *,
    organization_id: UUID,
    transmission: object,
    transcript: object,
    events: list[OperationalEvent],
) -> None:
    transmission_payload = {
        "id": str(transmission.id),
        "site_id": str(transmission.site_id),
        "agent_id": str(transmission.agent_id) if transmission.agent_id else None,
        "channel_id": str(transmission.channel_id) if transmission.channel_id else None,
        "source_type": transmission.source_type,
        "source_message_id": transmission.source_message_id,
        "created_at": transmission.created_at.isoformat(),
    }
    transcript_payload = {
        "id": str(transcript.id),
        "transmission_id": str(transcript.transmission_id),
        "normalized_text": transcript.normalized_text,
        "provider": transcript.provider,
        "created_at": transcript.created_at.isoformat(),
    }
    messages: list[tuple[str, str, dict[str, object]]] = [
        ("transmissions", "radio.transmission.created", transmission_payload),
        ("transcripts", "transcript.created", transcript_payload),
    ]
    messages.extend(("events", "event.created", _event_data(item)) for item in events)
    for topic, event_type, payload in messages:
        try:
            await publish_event(
                settings,
                organization_id=organization_id,
                topic=topic,
                event_type=event_type,
                payload=payload,
            )
        except Exception:
            # Persistence remains authoritative. Realtime delivery is best-effort until a durable
            # outbox is introduced in a later infrastructure phase.
            continue


@simulate_app.command("radio")
def simulate_radio(
    organization: str = typer.Option(..., "--organization"),
    site: str = typer.Option(..., "--site"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Feed deterministic sample radio traffic through the same production processing pipeline."""

    conversation = [
        ("Patrol 4", "Dispatch, Patrol 4. Wind loading is visible near the ridgeline."),
        ("Dispatch", "Copy Patrol 4. Which aspect?"),
        ("Patrol 4", "East facing, roughly ninety-eight hundred feet."),
        ("Dispatch", "Copy."),
        ("Patrol 7", "Heading up to take a look."),
    ]

    async def run() -> list[dict[str, object]]:
        settings = _load_settings()
        session_factory = create_session_factory(settings)
        async with session_factory() as session:
            organization_id, selected_site = await _resolve_site(
                session, organization=organization, site=site
            )
            selected_agent = await session.scalar(
                select(Agent)
                .where(
                    Agent.organization_id == organization_id,
                    Agent.site_id == selected_site.id,
                    Agent.enabled.is_(True),
                )
                .order_by(Agent.created_at)
                .limit(1)
            )
            results: list[dict[str, object]] = []
            for callsign, text in conversation:
                transmission, transcript, events, _duplicate = await ingest_transmission(
                    session,
                    settings=settings,
                    organization_id=organization_id,
                    payload=TransmissionCreateRequest(
                        site_id=selected_site.id,
                        agent_id=selected_agent.id if selected_agent else None,
                        callsign=callsign,
                        text=text,
                        source="simulator",
                        source_message_id=f"sim-{uuid4()}",
                    ),
                )
                await session.commit()
                await _publish_simulated_records(
                    settings,
                    organization_id=organization_id,
                    transmission=transmission,
                    transcript=transcript,
                    events=events,
                )
                results.extend(_event_data(item) for item in events)
            return results

    try:
        results = asyncio.run(run())
    except TerraSatchError as error:
        typer.echo(f"Error [{error.code}]: {error.message}", err=True)
        raise typer.Exit(code=1) from error

    if as_json:
        _emit(results, as_json=True)
        return
    typer.echo("TerraSatch radio simulation complete\n")
    for item in results:
        typer.echo(f"{item['event_type']:<18} {item['summary']}")
