"""Demo and organization profile commands layered onto the edge receiver CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from terrasatch.cli.edge import edge_app, rtl_capture
from terrasatch.edge.client import EdgeApiClient
from terrasatch.edge.devices import discover_receivers, select_receiver
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


@edge_app.command("capture")
def capture(
    frequency_hz: Annotated[int, typer.Option("--frequency-hz", min=1)],
    output: Annotated[Path, typer.Option("--output")] = Path("terrasatch-rx.wav"),
    seconds: Annotated[float, typer.Option("--seconds", min=0.5, max=120)] = 10.0,
    device: Annotated[str | None, typer.Option("--device")] = None,
    modulation: Annotated[str, typer.Option("--modulation")] = "fm",
    gain_db: Annotated[float | None, typer.Option("--gain-db")] = None,
    squelch: Annotated[int | None, typer.Option("--squelch", min=0)] = None,
    ppm: Annotated[int | None, typer.Option("--ppm", min=-250, max=250)] = None,
) -> None:
    """Use the configured/auto receiver and capture a short receive-only WAV."""

    profile = load_edge_profile()
    try:
        selected = select_receiver(discover_receivers(), backend=profile.backend)
    except Exception as error:
        typer.echo(f"Receiver selection failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    if selected.backend != "rtl":
        typer.echo(
            f"{selected.name} is recognized, but its TerraListen audio adapter is not enabled yet.",
            err=True,
        )
        raise typer.Exit(code=2)
    rtl_capture(
        frequency_hz=frequency_hz,
        output=output,
        seconds=seconds,
        device=device or profile.device_id,
        modulation=modulation,
        gain_db=gain_db,
        squelch=squelch,
        ppm=ppm,
        submit_text=None,
        site=None,
        callsign=None,
        api_base_url=None,
    )


@edge_app.command("demo")
def demo(
    frequency_hz: Annotated[int, typer.Option("--frequency-hz", min=1)],
    output: Annotated[Path, typer.Option("--output")] = Path("terrasatch-demo.wav"),
    seconds: Annotated[float, typer.Option("--seconds", min=0.5, max=120)] = 10.0,
    text: Annotated[
        str | None,
        typer.Option("--text", help="Optional operator-reviewed transcript; not automatic STT."),
    ] = None,
    site: Annotated[UUID | None, typer.Option("--site")] = None,
    callsign: Annotated[str | None, typer.Option("--callsign")] = None,
) -> None:
    """Plug in, capture locally, and optionally submit a connected demo without choosing an org."""

    capture(frequency_hz=frequency_hz, output=output, seconds=seconds)
    if text is None:
        typer.echo("demo: local capture complete; API submission skipped")
        return
    profile = load_edge_profile()
    destination = site or profile.site_id
    if destination is None or not os.getenv("TERRASATCH_EDGE_API_KEY", "").strip():
        typer.echo(
            "demo: local capture complete; API submission skipped because no demo site/API key is configured"
        )
        return
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
    typer.echo(f"demo: API submission complete; events={len(payload.get('events', []))}")
    typer.echo("organization: derived from API credential")


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
