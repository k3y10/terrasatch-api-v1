"""Capability and heartbeat reporting for connected TerraSatch Edge nodes."""

from __future__ import annotations

import time
from typing import Annotated

import typer

from terrasatch.cli.edge import edge_app
from terrasatch.edge.client import EdgeApiClient
from terrasatch.edge.devices import discover_receivers
from terrasatch.edge.profile import load_edge_profile


def _capability_payload() -> tuple[list[dict[str, object]], list[str]]:
    inventory: list[dict[str, object]] = []
    capabilities: set[str] = set()

    for receiver in discover_receivers():
        inventory.append(
            {
                "provider": receiver.backend,
                "name": receiver.name,
                "device_id": receiver.device_id,
                "capture_ready": receiver.capture_ready,
                "detail": receiver.detail,
            }
        )
        capabilities.add(f"provider:{receiver.backend}")
        if receiver.backend == "rtl" and receiver.capture_ready:
            capabilities.update({"radio:receive", "audio:capture"})
        if receiver.backend == "hackrf":
            # Discovery is intentionally distinct from a TerraListen capture/TX adapter.
            capabilities.add("hardware:hackrf")

    return inventory, sorted(capabilities)


def _report_once() -> None:
    profile = load_edge_profile()
    inventory, capabilities = _capability_payload()

    try:
        payload = EdgeApiClient.from_environment(base_url=profile.api_base_url).heartbeat(
            hardware_inventory=inventory,
            capabilities=capabilities,
        )
    except Exception as error:
        typer.echo(f"Edge capability sync failed: {error}", err=True)
        raise typer.Exit(code=1) from error

    device = payload.get("device", {})
    if not isinstance(device, dict):
        device = {}
    remote_config = device.get("remote_config", {})
    if not isinstance(remote_config, dict):
        remote_config = {}
    radio = remote_config.get("radio", {})
    if not isinstance(radio, dict):
        radio = {}
    ai = radio.get("ai_channel", {})
    if not isinstance(ai, dict):
        ai = {}

    typer.echo(f"device_id: {device.get('id', 'unknown')}")
    typer.echo(f"device_name: {device.get('name', 'unknown')}")
    typer.echo(
        "reported_capabilities: "
        + (", ".join(capabilities) if capabilities else "none")
    )
    typer.echo(f"receive_enabled: {radio.get('receive_enabled', 'auto')}")
    typer.echo(f"transmit_enabled: {radio.get('transmit_enabled', False)}")
    typer.echo("transmit_policy: provider must report radio:transmit before admin can enable TX")
    typer.echo("ai_agent: " + str(ai.get("agent_name", "Satchy")))
    typer.echo("ai_channel_name: " + str(ai.get("name", "Satchy AI Channel")))
    typer.echo("ai_activation_phrase: " + str(ai.get("activation_phrase", "TerraSatch")))
    typer.echo("ai_logical_channel_id: " + str(ai.get("logical_channel_id") or "not bound"))
    typer.echo("ai_provider_channel: " + str(ai.get("provider_channel") or "not bound"))
    typer.echo("ai_frequency_hz: " + str(ai.get("frequency_hz") or "not configured"))
    typer.echo("ai_reply_route: " + str(ai.get("reply_route", "dashboard")))
    typer.echo(
        "ai_execution: policy only until the configured outbound provider/"
        "Edge adapter executes it"
    )


@edge_app.command("sync")
def sync(
    watch: Annotated[
        bool,
        typer.Option(
            "--watch",
            help="Keep sending registered-device heartbeats so Admin can show online health.",
        ),
    ] = False,
    interval_seconds: Annotated[
        int,
        typer.Option(
            "--interval-seconds",
            help="Heartbeat interval when --watch is enabled (5-300 seconds).",
        ),
    ] = 30,
) -> None:
    """Report provider inventory/capabilities and fetch current radio/AI policy."""

    if not 5 <= interval_seconds <= 300:
        raise typer.BadParameter("interval-seconds must be between 5 and 300")

    if watch:
        typer.echo(f"heartbeat_watch: active every {interval_seconds}s (Ctrl+C to stop)")

    while True:
        _report_once()
        if not watch:
            return
        typer.echo(f"next_heartbeat_in_seconds: {interval_seconds}")
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            typer.echo("heartbeat_watch: stopped")
            return
