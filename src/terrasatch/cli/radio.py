"""CLI operations for agents, channels, callsigns, events, and the software radio simulator."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
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
from terrasatch.radio.schemas import AgentCreateRequest, CallsignCreateRequest, ChannelCreateRequest, TransmissionCreateRequest
from terrasatch.radio.service import (
    create_agent,
    create_callsign,
    create_channel,
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
simulate_app = typer.Typer(help="Run deterministic TerraSatch simulation inputs.", no_args_is_help=True)


def register_radio_cli(root: typer.Typer) -> None:
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
        from terrasatch.errors import InvalidConfiguration

        raise InvalidConfiguration("Site was not found in the selected organization")
    return selected_org.id, selected_site


@agent_app.command("create")
def agent_create(
    name: str = typer.Option(..., "--name"),
    organization: str = typer.Option(..., "--organization"),
    site: str = typer.Option(..., "--site"),
    profile: str = typer.Option("general", "--profile"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
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
    }
    _emit(data if as_json else f"Created agent {item.name} ({item.id})", as_json=as_json)


@agent_app.command("list")
def agent_list(
    organization: str = typer.Option(..., "--organization"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        return await list_agents(session, organization_id=selected_org.id, limit=100, offset=0)

    items = _run_database(operation)
    data = [
        {"id": str(item.id), "site_id": str(item.site_id), "name": item.name, "profile": item.profile}
        for item in items
    ]
    _emit(data if as_json else ("No agents found." if not data else "\n".join(f"{row['id']}  {row['name']}  {row['profile']}" for row in data)), as_json=as_json)


@channel_app.command("create")
def channel_create(
    name: str = typer.Option(..., "--name"),
    organization: str = typer.Option(..., "--organization"),
    site: str = typer.Option(..., "--site"),
    agent_id: UUID | None = typer.Option(None, "--agent-id"),
    profile: str = typer.Option("general", "--profile"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
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
    data = {"id": str(item.id), "site_id": str(item.site_id), "name": item.name, "profile": item.profile}
    _emit(data if as_json else f"Created channel {item.name} ({item.id})", as_json=as_json)


@channel_app.command("list")
def channel_list(
    organization: str = typer.Option(..., "--organization"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        return await list_channels(session, organization_id=selected_org.id, limit=100, offset=0)

    items = _run_database(operation)
    data = [
        {"id": str(item.id), "site_id": str(item.site_id), "name": item.name, "profile": item.profile}
        for item in items
    ]
    _emit(data if as_json else ("No channels found." if not data else "\n".join(f"{row['id']}  {row['name']}  {row['profile']}" for row in data)), as_json=as_json)


@callsign_app.command("add")
def callsign_add(
    name: str = typer.Option(..., "--name"),
    organization: str = typer.Option(..., "--organization"),
    site: str | None = typer.Option(None, "--site"),
    alias: list[str] | None = typer.Option(None, "--alias"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
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
    data = {"id": str(item.id), "name": item.name, "aliases": item.aliases}
    _emit(data if as_json else f"Added callsign {item.name} ({item.id})", as_json=as_json)


@callsign_app.command("list")
def callsign_list(
    organization: str = typer.Option(..., "--organization"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        return await list_callsigns(session, organization_id=selected_org.id, limit=100, offset=0)

    items = _run_database(operation)
    data = [{"id": str(item.id), "name": item.name, "aliases": item.aliases} for item in items]
    _emit(data if as_json else ("No callsigns found." if not data else "\n".join(f"{row['id']}  {row['name']}" for row in data)), as_json=as_json)


@event_app.command("list")
def event_list(
    organization: str = typer.Option(..., "--organization"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    async def operation(session: AsyncSession, _settings: Settings):
        selected_org = await resolve_organization(session, organization)
        return await list_events(session, organization_id=selected_org.id, limit=100, offset=0)

    items: list[OperationalEvent] = _run_database(operation)
    data = [
        {
            "id": str(item.id),
            "event_type": item.event_type,
            "summary": item.summary,
            "callsign": item.callsign,
            "aspect": item.aspect,
            "elevation_ft": item.elevation_ft,
            "confidence": item.confidence,
            "transmission_id": str(item.transmission_id),
        }
        for item in items
    ]
    _emit(
        data if as_json else ("No events found." if not data else "\n".join(f"{row['id']}  {row['event_type']:<18} {row['summary']}" for row in data)),
        as_json=as_json,
    )


@simulate_app.command("radio")
def simulate_radio(
    organization: str = typer.Option(..., "--organization"),
    site: str = typer.Option(..., "--site"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Feed deterministic sample radio traffic through the production processing pipeline."""

    conversation = [
        ("Patrol 4", "Dispatch, Patrol 4. We're seeing shooting cracks near the ridgeline."),
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
                for event in events:
                    payload = {
                        "id": str(event.id),
                        "event_type": event.event_type,
                        "summary": event.summary,
                        "callsign": event.callsign,
                        "aspect": event.aspect,
                        "elevation_ft": event.elevation_ft,
                        "confidence": event.confidence,
                        "transmission_id": str(transmission.id),
                        "transcript_id": str(transcript.id),
                    }
                    try:
                        await publish_event(
                            settings,
                            organization_id=organization_id,
                            topic="events",
                            event_type="event.created",
                            payload=payload,
                        )
                    except Exception:
                        # Persistence remains the source of truth; realtime publication is best effort
                        # until a durable outbox is added in a later phase.
                        pass
                    results.append(payload)
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
