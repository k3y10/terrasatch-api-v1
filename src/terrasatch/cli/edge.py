"""Receive-only edge commands for Nooelec/RTL-SDR and field-radio acceptance testing."""

from __future__ import annotations

import json
import shlex
import wave
from pathlib import Path
from typing import Annotated
from uuid import UUID

import httpx
import typer

from terrasatch.config import Settings
from terrasatch.edge.audio import inspect_wav
from terrasatch.edge.client import submit_text_transmission
from terrasatch.edge.rtl import (
    RTLCaptureError,
    RTLReceiveConfig,
    RTLToolUnavailable,
    build_rtl_fm_command,
    capture_rtl_wav,
    find_rtl_tools,
    probe_rtl_device,
)

edge_app = typer.Typer(help="Operate receive-only radio edge diagnostics and capture tools.")


def register_edge_cli(app: typer.Typer) -> None:
    app.add_typer(edge_app, name="edge")


def _emit(payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(payload, indent=2, default=str))
        return
    for key, value in payload.items():
        typer.echo(f"{key}: {value}")


@edge_app.command("doctor")
def edge_doctor(
    check_api: Annotated[bool, typer.Option("--check-api", help="Also probe /health/ready.")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Report local RTL-SDR tooling and outbound API readiness without opening a radio."""

    settings = Settings()
    tools = find_rtl_tools()
    payload: dict[str, object] = {
        "receive_only": True,
        "rtl_test": tools["rtl_test"] or "missing",
        "rtl_fm": tools["rtl_fm"] or "missing",
        "api_base_url": str(settings.api_base_url),
        "edge_api_key_configured": settings.edge_api_key is not None,
        "stt_provider": settings.stt_provider,
        "automatic_stt_active": False,
    }
    if check_api:
        try:
            response = httpx.get(
                f"{str(settings.api_base_url).rstrip('/')}/health/ready",
                timeout=5,
            )
            payload["api_health_status"] = response.status_code
            payload["api_health"] = response.json().get("status", "unknown")
        except Exception as error:
            payload["api_health"] = "unavailable"
            payload["api_health_error"] = type(error).__name__
    _emit(payload, json_output=json_output)


@edge_app.command("devices")
def edge_devices(
    device: Annotated[str, typer.Option("--device", help="RTL device index or serial.")] = "0",
    timeout_seconds: Annotated[
        float,
        typer.Option("--timeout", min=0.5, max=10, help="Bounded receive probe duration."),
    ] = 2.0,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Open one RTL-SDR briefly with rtl_test and report whether receive access works."""

    try:
        ok, detail = probe_rtl_device(device=device, timeout_seconds=timeout_seconds)
    except RTLToolUnavailable as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    _emit({"device": device, "available": ok, "detail": detail}, json_output=json_output)
    if not ok:
        raise typer.Exit(code=1)


@edge_app.command("capture-rtl")
def edge_capture_rtl(
    frequency_hz: Annotated[int, typer.Option("--frequency-hz", min=1, help="Receive frequency in Hz.")],
    seconds: Annotated[float, typer.Option("--seconds", min=0.25, max=120)] = 8.0,
    output: Annotated[Path, typer.Option("--output", help="Destination WAV path.")] = Path(
        "terrasatch-rx.wav"
    ),
    sample_rate: Annotated[int, typer.Option("--sample-rate", min=8_000, max=300_000)] = 24_000,
    output_rate: Annotated[int, typer.Option("--output-rate", min=8_000, max=96_000)] = 24_000,
    device: Annotated[str, typer.Option("--device")] = "0",
    gain_db: Annotated[float | None, typer.Option("--gain-db")] = None,
    squelch: Annotated[int, typer.Option("--squelch", min=0, max=100)] = 0,
    modulation: Annotated[str, typer.Option("--modulation")] = "fm",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print argv without opening hardware.")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Capture a short receive-only RTL-SDR session as signed-16-bit mono WAV."""

    try:
        config = RTLReceiveConfig(
            frequency_hz=frequency_hz,
            sample_rate=sample_rate,
            output_rate=output_rate,
            device=device,
            gain_db=gain_db,
            squelch=squelch,
            modulation=modulation,
        )
        command = build_rtl_fm_command(config)
        if dry_run:
            _emit(
                {"receive_only": True, "command": shlex.join(command), "output": str(output)},
                json_output=json_output,
            )
            return
        result = capture_rtl_wav(config, seconds=seconds, output_path=output)
    except (RTLToolUnavailable, RTLCaptureError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    _emit({"receive_only": True, **result}, json_output=json_output)


@edge_app.command("inspect-wav")
def edge_inspect_wav(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect the WAV emitted by a receive capture before adding speech recognition."""

    try:
        payload = inspect_wav(path)
    except (OSError, wave.Error) as error:
        typer.echo(f"Unable to inspect WAV: {error}", err=True)
        raise typer.Exit(code=2) from error
    _emit(payload, json_output=json_output)


@edge_app.command("submit-text")
def edge_submit_text(
    site: Annotated[UUID, typer.Option("--site", help="Site UUID within the API-key tenant.")],
    text: Annotated[str, typer.Option("--text", help="Manual transcript/test phrase to ingest.")],
    callsign: Annotated[str | None, typer.Option("--callsign")] = None,
    source: Annotated[str, typer.Option("--source")] = "edge-manual",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Submit a manual transcript through the same API pipeline used by future STT output."""

    settings = Settings()
    if settings.edge_api_key is None:
        typer.echo(
            "TERRASATCH_EDGE_API_KEY is required and must contain an API key with edge:ingest scope.",
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        response = submit_text_transmission(
            base_url=str(settings.api_base_url),
            api_key=settings.edge_api_key.get_secret_value(),
            site_id=site,
            text=text,
            callsign=callsign,
            source=source,
        )
    except (ValueError, httpx.HTTPError) as error:
        typer.echo(f"Transmission submission failed: {error}", err=True)
        raise typer.Exit(code=2) from error
    _emit(response, json_output=json_output)


@edge_app.command("acceptance")
def edge_acceptance(
    frequency_hz: Annotated[int, typer.Option("--frequency-hz", min=1)],
    site: Annotated[UUID, typer.Option("--site")],
    text: Annotated[
        str,
        typer.Option(
            "--text",
            help="What you actually said on the test radio; this is manual until STT is added.",
        ),
    ],
    seconds: Annotated[float, typer.Option("--seconds", min=0.25, max=120)] = 8.0,
    output: Annotated[Path, typer.Option("--output")] = Path("terrasatch-bca-test.wav"),
    device: Annotated[str, typer.Option("--device")] = "0",
    callsign: Annotated[str | None, typer.Option("--callsign")] = None,
    squelch: Annotated[int, typer.Option("--squelch", min=0, max=100)] = 0,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Capture RF audio, then manually inject the spoken phrase through the canonical API.

    This proves receiver access + audio capture + API/TerraEngine persistence. It intentionally does
    not claim automatic speech-to-text validation; STT/VAD is the next edge milestone.
    """

    settings = Settings()
    if settings.edge_api_key is None:
        typer.echo("TERRASATCH_EDGE_API_KEY is required for acceptance testing.", err=True)
        raise typer.Exit(code=2)
    try:
        config = RTLReceiveConfig(frequency_hz=frequency_hz, device=device, squelch=squelch)
        capture = capture_rtl_wav(config, seconds=seconds, output_path=output)
        submitted = submit_text_transmission(
            base_url=str(settings.api_base_url),
            api_key=settings.edge_api_key.get_secret_value(),
            site_id=site,
            text=text,
            callsign=callsign,
            source="edge-bca-manual",
        )
    except (RTLToolUnavailable, RTLCaptureError, ValueError, httpx.HTTPError) as error:
        typer.echo(f"Acceptance test failed: {error}", err=True)
        raise typer.Exit(code=2) from error

    payload = {
        "receive_only": True,
        "rf_audio_captured": True,
        "automatic_stt_validated": False,
        "manual_transcript_submitted": True,
        "capture": capture,
        "api": submitted,
    }
    _emit(payload, json_output=json_output)
