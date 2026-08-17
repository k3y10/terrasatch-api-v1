"""Health and capability summaries for registered TerraSatch Edge devices."""

from __future__ import annotations

from datetime import UTC, datetime

from terrasatch.admin.ai_channel import ai_channel_config
from terrasatch.admin.commands import (
    device_supports_receive,
    device_supports_transmit,
    radio_config,
    radio_mode,
)
from terrasatch.edge.models import EdgeDevice

ONLINE_AFTER_SECONDS = 120
STALE_AFTER_SECONDS = 900


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def device_health(
    device: EdgeDevice,
    *,
    now: datetime | None = None,
) -> tuple[str, int | None]:
    """Return a UI health state and last-seen age for one registered Edge device."""

    if not bool(getattr(device, "enabled", True)):
        return "disabled", None
    last_seen_at = getattr(device, "last_seen_at", None)
    if last_seen_at is None:
        return "never", None

    reference = now or datetime.now(UTC)
    age_seconds = max(0, int((reference - _aware(last_seen_at)).total_seconds()))
    if age_seconds <= ONLINE_AFTER_SECONDS:
        return "online", age_seconds
    if age_seconds <= STALE_AFTER_SECONDS:
        return "stale", age_seconds
    return "offline", age_seconds


def _hardware_summary(device: EdgeDevice) -> tuple[str, str, int]:
    inventory = [
        item
        for item in (getattr(device, "hardware_inventory", []) or [])
        if isinstance(item, dict)
    ]
    if not inventory:
        return "No radio hardware reported", "none", 0

    def score(item: dict[str, object]) -> int:
        provider = str(item.get("provider") or "").lower()
        name = str(item.get("name") or "").lower()
        detail = f"{provider} {name}"
        if provider in {"rtl", "rtl-sdr"} or any(
            token in detail for token in ("nooelec", "nesdr", "rtl283", "rtl-sdr")
        ):
            return 100
        if provider == "hackrf" or "hackrf" in detail:
            return 90
        if any(token in detail for token in ("radio", "receiver", "sdr")):
            return 70
        if bool(item.get("capture_ready")):
            return 60
        return 0

    primary = max(inventory, key=score)
    primary_name = str(primary.get("name") or primary.get("provider") or "Unknown hardware").strip()
    provider = str(primary.get("provider") or "unknown").strip()
    return primary_name, provider, len(inventory)


def device_status_payload(
    device: EdgeDevice,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Serialize a registered Edge device for the session-protected fleet UI."""

    health, age_seconds = device_health(device, now=now)
    radio = radio_config(device)
    ai = ai_channel_config(device)
    rx_supported = device_supports_receive(device)
    tx_supported = device_supports_transmit(device)
    rx_enabled = rx_supported and bool(radio.get("receive_enabled", rx_supported))
    tx_enabled = tx_supported and bool(radio.get("transmit_enabled", False))
    last_seen_at = getattr(device, "last_seen_at", None)
    primary_hardware, provider, hardware_count = _hardware_summary(device)

    return {
        "id": str(device.id),
        "site_id": str(device.site_id),
        "name": device.name,
        "hostname": getattr(device, "hostname", None),
        "platform": getattr(device, "platform", None),
        "architecture": getattr(device, "architecture", None),
        "agent_version": getattr(device, "agent_version", None),
        "enabled": bool(getattr(device, "enabled", True)),
        "health": health,
        "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
        "age_seconds": age_seconds,
        "hardware": primary_hardware,
        "primary_hardware": primary_hardware,
        "provider": provider,
        "hardware_count": hardware_count,
        "hardware_inventory": getattr(device, "hardware_inventory", []) or [],
        "capabilities": getattr(device, "capabilities", []) or [],
        "rx_supported": rx_supported,
        "tx_supported": tx_supported,
        "rx_enabled": rx_enabled,
        "tx_enabled": tx_enabled,
        "mode": radio_mode(device),
        "ai_channel": {
            "name": ai.get("name", "Satchy AI Channel"),
            "agent_name": ai.get("agent_name", "Satchy"),
            "activation_phrase": ai.get("activation_phrase", "TerraSatch"),
            "logical_channel_id": ai.get("logical_channel_id"),
            "provider_channel": ai.get("provider_channel"),
            "frequency_hz": ai.get("frequency_hz"),
            "reply_route": ai.get("reply_route", "dashboard"),
        },
    }


def fleet_summary(devices: list[dict[str, object]]) -> dict[str, int]:
    """Count current fleet health, site coverage, and radio capabilities."""

    counts = {
        "total": len(devices),
        "online": 0,
        "stale": 0,
        "offline": 0,
        "never": 0,
        "disabled": 0,
        "sites": len({str(device.get("site_id")) for device in devices if device.get("site_id")}),
        "rx_capable": sum(bool(device.get("rx_supported")) for device in devices),
        "tx_capable": sum(bool(device.get("tx_supported")) for device in devices),
        "attention": 0,
    }
    for device in devices:
        health = str(device.get("health", "never"))
        if health in counts:
            counts[health] += 1
        if health in {"stale", "offline", "never"}:
            counts["attention"] += 1
    return counts
