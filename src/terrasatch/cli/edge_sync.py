"""Capability reporting for connected TerraSatch Edge nodes."""

from __future__ import annotations

import typer

from terrasatch.cli.edge import edge_app
from terrasatch.edge.client import EdgeApiClient
from terrasatch.edge.devices import discover_receivers
from terrasatch.edge.profile import load_edge_profile


@edge_app.command("sync")
def sync() -> None:
    """Report provider inventory/capabilities and fetch the current remote radio policy."""

    profile = load_edge_profile()
    receivers = discover_receivers()
    inventory: list[dict[str, object]] = []
    capabilities: set[str] = set()

    for receiver in receivers:
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
            # Hardware discovery alone does not mean a TerraListen TX adapter exists.
            capabilities.add("hardware:hackrf")

    try:
        payload = EdgeApiClient.from_environment(
            base_url=profile.api_base_url
        ).heartbeat(
            hardware_inventory=inventory,
            capabilities=sorted(capabilities),
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

    typer.echo(f"device_id: {device.get('id', 'unknown')}")
    typer.echo(f"device_name: {device.get('name', 'unknown')}")
    typer.echo(
        "reported_capabilities: "
        + (", ".join(sorted(capabilities)) if capabilities else "none")
    )
    typer.echo(f"receive_enabled: {radio.get('receive_enabled', 'auto')}")
    typer.echo(f"transmit_enabled: {radio.get('transmit_enabled', False)}")
    typer.echo(
        "transmit_policy: provider must report radio:transmit before admin can enable TX"
    )
