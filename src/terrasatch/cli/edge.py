"""Receive-only local edge commands for RTL-SDR and radio acceptance testing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from terrasatch.edge.audio import inspect_wav
from terrasatch.edge.client import EdgeApiClient
from terrasatch.edge.rtl import RtlCaptureConfig, capture_rtl_fm, probe_rtl_device
from terrasatch.edge.tools import inspect_edge_tools

edge_app = typer.Typer(help="Operate receive-only field edge tools.", no_args_is_help=True)
rtl_app = typer.Typer(help="Detect and capture from RTL-SDR compatible receivers.", no_args_is_help=True)
audio_app = typer.Typer(help="Inspect locally captured receive audio.", no_args_is_help=True)
api_app = typer.Typer(help="Verify the edge machine can reach the TerraSatch API.", no_args_is_help=True)


def register_edge_cli(root: typer.Typer) -> None:
    edge_app.add_typer(rtl_app, name="rtl")
    edge_app.add_typer(audio_app, name="audio")
    edge_app.add_typer(api_app, name="api")
    root.add_typer(edge_app, name="edge")


def _fail(error: Exception) -> None:
    typer.echo(f"Edge command failed: {error}", err=True)
    raise typer.Exit(code=1) from error


@edge_app.command("doctor")
def edge_doctor() -> None:
    """Report local receiver dependencies without touching a radio device."""

    statuses = inspect_edge_tools()
    for item in statuses:
        marker = "OK" if item.available else "MISSING"
        location = item.path or "not found on PATH"
        typer.echo(f"[{marker}] {item.name}: {location} — {item.required_for}")
    typer.echo("Receive-only boundary: no TerraSatch edge command keys or transmits a radio.")


@rtl_app.command("devices")
def rtl_devices(
    device: Annotated[str | None, typer.Option("--device", help="RTL-SDR device index or serial.")] = None,
) -> None:
    """Run a short bounded rtl_test probe and show receiver startup diagnostics."""

    try:
        typer.echo(probe_rtl_device(device=device))
    except Exception as error:
        _fail(error)


@rtl_app.command("capture")
def rtl_capture(
    frequency_hz: Annotated[int, typer.Option("--frequency-hz", min=1, help="Receive frequency in Hz.")],
    output: Annotated[Path, typer.Option("--output", help="Destination mono WAV path.")],
    seconds: Annotated[float, typer.Option("--seconds", min=0.5, max=120)] = 10.0,
    device: Annotated[str | None, typer.Option("--device", help="RTL-SDR device index or serial.")] = None,
    modulation: Annotated[str, typer.Option("--modulation", help="Receive demodulation: fm, am, or wbfm.")] = "fm",
    gain_db: Annotated[float | None, typer.Option("--gain-db", help="Optional manual receive gain in dB.")] = None,
    squelch: Annotated[int | None, typer.Option("--squelch", min=0)] = None,
    submit_text: Annotated[
        str | None,
        typer.Option(
            "--submit-text",
            help="Operator-supplied transcript to submit after capture; this is not automatic STT.",
        ),
    ] = None,
    site: Annotated[UUID | None, typer.Option("--site", help="Site UUID required with --submit-text.")] = None,
    callsign: Annotated[str | None, typer.Option("--callsign")] = None,
    api_base_url: Annotated[str | None, typer.Option("--api-base-url")] = None,
) -> None:
    """Capture receive-side SDR audio and optionally bridge operator text into the production API."""

    if submit_text and site is None:
        raise typer.BadParameter("--site is required when --submit-text is used")
    config = RtlCaptureConfig(
        frequency_hz=frequency_hz,
        duration_seconds=seconds,
        device=device,
        modulation=modulation,
        gain_db=gain_db,
        squelch=squelch,
    )
    try:
        captured = capture_rtl_fm(config, output)
        diagnostics = inspect_wav(captured)
        typer.echo(
            f"Captured {diagnostics.duration_seconds:.2f}s to {captured} "
            f"({diagnostics.sample_rate_hz} Hz, peak={diagnostics.peak})"
        )
        if submit_text and site is not None:
            client = EdgeApiClient.from_environment(base_url=api_base_url)
            result = client.submit_text(
                site_id=site,
                text=submit_text,
                callsign=callsign,
                source="edge-rtl",
            )
            event_count = len(result.get("events", []))
            typer.echo(f"Submitted operator transcript through production ingest; events={event_count}")
    except Exception as error:
        _fail(error)


@audio_app.command("inspect")
def audio_inspect(
    path: Annotated[Path, typer.Argument(help="PCM WAV capture to inspect.")],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect WAV duration, format, RMS, and peak without external audio libraries."""

    try:
        report = inspect_wav(path)
    except Exception as error:
        _fail(error)
        return
    payload = {
        "path": str(report.path),
        "duration_seconds": round(report.duration_seconds, 3),
        "sample_rate_hz": report.sample_rate_hz,
        "channels": report.channels,
        "sample_width_bytes": report.sample_width_bytes,
        "frame_count": report.frame_count,
        "rms": round(report.rms, 2) if report.rms is not None else None,
        "peak": report.peak,
        "has_audio_energy": report.has_audio_energy,
    }
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            typer.echo(f"{key}: {value}")


@api_app.command("check")
def api_check(
    base_url: Annotated[str | None, typer.Option("--base-url")] = None,
) -> None:
    """Authenticate the local edge machine without printing its API key."""

    try:
        payload = EdgeApiClient.from_environment(base_url=base_url).check()
    except Exception as error:
        _fail(error)
        return
    scopes = payload.get("scopes", [])
    typer.echo(f"organization_id: {payload.get('organization_id')}")
    typer.echo(f"scopes: {', '.join(scopes) if isinstance(scopes, list) else scopes}")
    typer.echo(f"edge:ingest: {'ready' if isinstance(scopes, list) and ('edge:ingest' in scopes or 'admin' in scopes) else 'missing'}")


@edge_app.command("submit-text")
def submit_text(
    site: Annotated[UUID, typer.Option("--site", help="Destination site UUID.")],
    text: Annotated[str, typer.Option("--text", help="Operator-reviewed transcript text.")],
    callsign: Annotated[str | None, typer.Option("--callsign")] = None,
    agent: Annotated[UUID | None, typer.Option("--agent")] = None,
    channel: Annotated[UUID | None, typer.Option("--channel")] = None,
    source_message_id: Annotated[str | None, typer.Option("--source-message-id")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Submit operator-reviewed text through the same production transmission pipeline."""

    try:
        payload = EdgeApiClient.from_environment(base_url=base_url).submit_text(
            site_id=site,
            text=text,
            callsign=callsign,
            agent_id=agent,
            channel_id=channel,
            source_message_id=source_message_id,
        )
    except Exception as error:
        _fail(error)
        return
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        transmission = payload.get("transmission", {})
        typer.echo(f"transmission_id: {transmission.get('id') if isinstance(transmission, dict) else transmission}")
        typer.echo(f"events: {len(payload.get('events', []))}")
        typer.echo(f"duplicate: {payload.get('duplicate', False)}")
