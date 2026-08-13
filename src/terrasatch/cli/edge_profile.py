"""Demo and organization profile commands layered onto the edge receiver CLI."""

from __future__ import annotations

import json
import os
from typing import Annotated
from uuid import UUID

import typer

from terrasatch.cli.edge import edge_app
from terrasatch.edge.client import EdgeApiClient
from terrasatch.edge.devices import discover_receivers
from terrasatch.edge.profile import EdgeProfile, load_edge_profile, save_edge_profile


@edge_app.command("setup")
def setup(
    mode: Annotated[str, typer.Option("--mode", help="demo or organization")] = "demo",
    site: Annotated[
        UUID | None,
        typer.Option("--site", help="Optional site UUID; required for organization mode."),
    ] = None,
    backend: Annotated[str, typer.Option("--backend", help="auto, rtl, or hackrf")] = "auto",
    device: Annotated[str | None, typer.Option("--device")] = None,
    api_base_url: Annotated[str, typer.Option("--api-base-url")] = "https://api.terrasatch.com",
) -> None:
    """Save non-secret edge preferences; demo mode needs no organization or credential."""

    profile = EdgeProfile(
        mode=mode,
        api_base_url=api_base_url,
        site_id=site,
        backend=backend,
        device_id=device,
    )
    try:
        path = save_edge_profile(profile)
    except Exception as error:
        typer.echo(f"Edge setup failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"profile: {path}")
    typer.echo(f"mode: {profile.mode}")
    typer.echo(f"backend: {profile.backend}")
    typer.echo(f"site_id: {profile.site_id or 'not configured'}")
    typer.echo("organization: derived from the API credential when connected")
    typer.echo("credential: keep TERRASATCH_EDGE_API_KEY outside this profile")


@edge_app.command("status")
def status() -> None:
    """Show the local edge profile without exposing its API credential."""

    try:
        profile = load_edge_profile()
    except Exception as error:
        typer.echo(f"Unable to load edge profile: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"mode: {profile.mode}")
    typer.echo(f"backend: {profile.backend}")
    typer.echo(f"device: {profile.device_id or 'auto'}")
    typer.echo(f"site_id: {profile.site_id or 'not configured'}")
    typer.echo(f"api_base_url: {profile.api_base_url}")
    typer.echo(f"api_key_configured: {bool(os.getenv('TERRASATCH_EDGE_API_KEY', '').strip())}")
    typer.echo("organization: derived from the API credential when connected")


@edge_app.command("detect")
def detect() -> None:
    """Show available receiver backends without requiring an organization."""

    devices = discover_receivers()
    if not devices:
        typer.echo("No compatible receiver backend tooling detected.")
        return
    for device in devices:
        typer.echo(
            f"{device.name}: backend={device.backend} capture_ready={device.capture_ready} — {device.detail}"
        )


@edge_app.command("demo-submit")
def demo_submit(
    text: Annotated[str, typer.Option("--text", help="Operator-reviewed transcript text.")],
    site: Annotated[UUID | None, typer.Option("--site")] = None,
    callsign: Annotated[str | None, typer.Option("--callsign")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Optionally send a demo capture transcript without selecting an organization."""

    profile = load_edge_profile()
    destination = site or profile.site_id
    if destination is None:
        raise typer.BadParameter("Configure a demo site once with edge setup or provide --site")
    try:
        payload = EdgeApiClient.from_environment(base_url=profile.api_base_url).submit_text(
            site_id=destination,
            text=text,
            callsign=callsign,
            source="edge-demo",
        )
    except Exception as error:
        typer.echo(f"Demo submission failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"events: {len(payload.get('events', []))}")
        typer.echo("organization: derived from API credential")
