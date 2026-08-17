"""Satchy AI radio-channel policy stored on an Edge device.

The AI channel is a logical TerraListen control-plane concept. It may be bound to a
provider channel or RF frequency, but this module never performs RF transmission.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.edge.models import EdgeDevice
from terrasatch.edge.schemas import EdgeDeviceUpdateRequest
from terrasatch.edge.service import update_device
from terrasatch.errors import InvalidConfiguration
from terrasatch.radio.service import get_channel

_DEFAULT_AI_CHANNEL: dict[str, object] = {
    "name": "Satchy AI Channel",
    "agent_name": "Satchy",
    "activation_phrase": "TerraSatch",
    "logical_channel_id": None,
    "provider_channel": None,
    "frequency_hz": None,
    "modulation": "fm",
    "reply_route": "dashboard",
    "rf_reply_enabled": False,
}

_TX_CAPABILITIES = {"radio:transmit", "radio:tx", "tx", "transmit", "ptt"}
_ALLOWED_REPLY_ROUTES = {"dashboard", "push", "tts", "rf"}
_ALLOWED_MODULATIONS = {"fm", "nfm", "wbfm", "am"}


def _supports_transmit(device: EdgeDevice) -> bool:
    capabilities = {str(item).lower() for item in device.capabilities}
    return bool(capabilities & _TX_CAPABILITIES)


def ai_channel_config(device: EdgeDevice) -> dict[str, object]:
    config = dict(device.remote_config or {})
    radio = config.get("radio")
    radio_dict = dict(radio) if isinstance(radio, dict) else {}
    ai = radio_dict.get("ai_channel")
    ai_dict = dict(ai) if isinstance(ai, dict) else {}
    return {**_DEFAULT_AI_CHANNEL, **ai_dict}


def ai_channel_lines(device: EdgeDevice) -> list[str]:
    ai = ai_channel_config(device)
    return [
        f"AI       {ai['name']}",
        f"AGENT    {ai['agent_name']}",
        f"TRIGGER  {ai['activation_phrase']}",
        f"CHANNEL  {ai['logical_channel_id'] or 'not bound'}",
        f"PROVIDER {ai['provider_channel'] or 'not bound'}",
        f"FREQ     {ai['frequency_hz'] or 'not configured'}",
        f"MOD      {ai['modulation']}",
        f"REPLY    {ai['reply_route']} (policy)",
        "EXEC     Edge/provider adapter required; core never autonomously transmits RF",
    ]


def _confirmed(args: list[str]) -> bool:
    return "--confirm" in args


async def _save(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device: EdgeDevice,
    ai: dict[str, object],
) -> EdgeDevice:
    config = dict(device.remote_config or {})
    radio = config.get("radio")
    radio_dict = dict(radio) if isinstance(radio, dict) else {}
    radio_dict["ai_channel"] = ai
    config["radio"] = radio_dict
    return await update_device(
        session,
        organization_id=organization_id,
        device_id=device.id,
        payload=EdgeDeviceUpdateRequest(remote_config=config),
    )


async def run_ai_channel_command(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device: EdgeDevice,
    args: list[str],
) -> list[str]:
    if not args or args[0].lower() in {"show", "status"}:
        return ai_channel_lines(device)

    action = args[0].lower()
    ai = ai_channel_config(device)

    if action == "bind" and len(args) >= 2:
        try:
            channel_id = UUID(args[1])
        except ValueError as exc:
            raise InvalidConfiguration("channel_id must be a UUID") from exc
        channel = await get_channel(
            session,
            organization_id=organization_id,
            channel_id=channel_id,
        )
        if channel.site_id != device.site_id:
            raise InvalidConfiguration("AI channel and Edge device must belong to the same site")
        ai["logical_channel_id"] = str(channel.id)
        updated = await _save(session, organization_id=organization_id, device=device, ai=ai)
        return [
            f"[ok] {updated.name}: Satchy bound to logical channel {channel.name} ({channel.id})"
        ]

    if action == "unbind":
        if not _confirmed(args):
            raise InvalidConfiguration(
                "Confirmation required: rerun with --confirm to unbind Satchy"
            )
        ai["logical_channel_id"] = None
        updated = await _save(session, organization_id=organization_id, device=device, ai=ai)
        return [f"[ok] {updated.name}: Satchy logical channel unbound"]

    if action in {"name", "agent", "trigger", "activation"} and len(args) >= 2:
        value = " ".join(item for item in args[1:] if item != "--confirm").strip()
        if not value:
            raise InvalidConfiguration(f"{action} value cannot be empty")
        key = {
            "name": "name",
            "agent": "agent_name",
            "trigger": "activation_phrase",
            "activation": "activation_phrase",
        }[action]
        ai[key] = value
        updated = await _save(session, organization_id=organization_id, device=device, ai=ai)
        return [f"[ok] {updated.name}: {key} -> {value}"]

    if action in {"provider-channel", "provider"} and len(args) >= 2:
        value = " ".join(item for item in args[1:] if item != "--confirm").strip()
        ai["provider_channel"] = None if value.lower() in {"off", "none", "clear"} else value
        updated = await _save(session, organization_id=organization_id, device=device, ai=ai)
        return [f"[ok] {updated.name}: provider channel -> {ai['provider_channel'] or 'not bound'}"]

    if action == "frequency" and len(args) >= 2:
        value = args[1].lower()
        if value in {"off", "none", "clear"}:
            ai["frequency_hz"] = None
        else:
            try:
                frequency_hz = int(value)
            except ValueError as exc:
                raise InvalidConfiguration("frequency must be an integer in Hz or 'off'") from exc
            if not 100_000 <= frequency_hz <= 6_000_000_000:
                raise InvalidConfiguration("frequency must be between 100 kHz and 6 GHz")
            ai["frequency_hz"] = frequency_hz
        updated = await _save(session, organization_id=organization_id, device=device, ai=ai)
        frequency_display = ai["frequency_hz"] or "not configured"
        return [f"[ok] {updated.name}: AI channel frequency -> {frequency_display}"]

    if action == "modulation" and len(args) >= 2:
        modulation = args[1].lower()
        if modulation not in _ALLOWED_MODULATIONS:
            raise InvalidConfiguration("modulation must be one of: fm, nfm, wbfm, am")
        ai["modulation"] = modulation
        updated = await _save(session, organization_id=organization_id, device=device, ai=ai)
        return [f"[ok] {updated.name}: AI channel modulation -> {modulation}"]

    if action == "reply" and len(args) >= 2:
        route = args[1].lower()
        if route not in _ALLOWED_REPLY_ROUTES:
            raise InvalidConfiguration("reply route must be one of: dashboard, push, tts, rf")
        if route == "rf":
            raw_radio = (device.remote_config or {}).get("radio")
            radio = dict(raw_radio) if isinstance(raw_radio, dict) else {}
            if not _supports_transmit(device):
                raise InvalidConfiguration(
                    "RF reply unavailable: Edge provider has not reported radio:transmit"
                )
            if not bool(radio.get("transmit_enabled", False)):
                raise InvalidConfiguration("RF reply unavailable: enable Edge TX policy first")
            if not _confirmed(args):
                raise InvalidConfiguration(
                    "Confirmation required: rerun with --confirm to configure RF reply policy"
                )
            ai["rf_reply_enabled"] = True
        else:
            ai["rf_reply_enabled"] = False
        ai["reply_route"] = route
        updated = await _save(session, organization_id=organization_id, device=device, ai=ai)
        lines = [f"[ok] {updated.name}: Satchy reply route -> {route}"]
        if route in {"push", "tts"}:
            lines.append(
                "[note] route is control-plane policy until an outbound provider is installed"
            )
        if route == "rf":
            lines.append("[note] RF execution remains Edge-provider controlled and operator-gated")
        return lines

    raise InvalidConfiguration(
        "Usage: edge ai <device> show|bind|unbind|name|agent|trigger|"
        "provider-channel|frequency|modulation|reply ..."
    )
