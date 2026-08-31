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

_DEFAULT_ACTION_TYPES = (
    "reply_radio",
    "ask_clarification",
    "create_observation",
    "update_event",
    "notify_team",
    "generate_report",
    "emergency_review",
)
_DEFAULT_APPROVER_ROLES = ("owner", "admin", "operator")

DEFAULT_AI_CHANNEL: dict[str, object] = {
    "name": "Satchy AI Channel",
    "agent_name": "Satchy",
    "activation_phrase": "TerraSatch",
    "activation_required": False,
    "activation_position": "start",
    "activation_case_sensitive": False,
    "logical_channel_id": None,
    "provider_channel": None,
    "frequency_hz": None,
    "modulation": "fm",
    "reply_route": "dashboard",
    "rf_reply_enabled": False,
    "response_mode": "suggest",
    "allowed_action_types": list(_DEFAULT_ACTION_TYPES),
    "authorized_approver_roles": list(_DEFAULT_APPROVER_ROLES),
    "max_reply_seconds": 15,
    "response_cooldown_seconds": 10,
    "conversation_timeout_seconds": 300,
    "emergency_detection_enabled": True,
    "emergency_auto_broadcast": False,
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
    return {**DEFAULT_AI_CHANNEL, **ai_dict}


def default_ai_channel_config() -> dict[str, object]:
    """Return an isolated copy of the safe, suggest-only policy."""

    return {
        **DEFAULT_AI_CHANNEL,
        "allowed_action_types": list(_DEFAULT_ACTION_TYPES),
        "authorized_approver_roles": list(_DEFAULT_APPROVER_ROLES),
    }


def rf_reply_policy_allows(device: EdgeDevice) -> bool:
    """Require both device capability and explicit API/AI-channel TX policy."""

    raw_radio = (device.remote_config or {}).get("radio")
    radio = dict(raw_radio) if isinstance(raw_radio, dict) else {}
    ai = ai_channel_config(device)
    return (
        _supports_transmit(device)
        and bool(radio.get("transmit_enabled", False))
        and bool(ai.get("rf_reply_enabled", False))
    )


def ai_channel_lines(device: EdgeDevice) -> list[str]:
    ai = ai_channel_config(device)
    allowed_actions = ai.get("allowed_action_types")
    if not isinstance(allowed_actions, list):
        allowed_actions = list(_DEFAULT_ACTION_TYPES)
    approver_roles = ai.get("authorized_approver_roles")
    if not isinstance(approver_roles, list):
        approver_roles = list(_DEFAULT_APPROVER_ROLES)
    return [
        f"AI       {ai['name']}",
        f"AGENT    {ai['agent_name']}",
        f"TRIGGER  {ai['activation_phrase']}",
        (
            f"GATE     {'required' if ai['activation_required'] else 'off'} "
            f"({ai['activation_position']})"
        ),
        f"CHANNEL  {ai['logical_channel_id'] or 'not bound'}",
        f"PROVIDER {ai['provider_channel'] or 'not bound'}",
        f"FREQ     {ai['frequency_hz'] or 'not configured'}",
        f"MOD      {ai['modulation']}",
        f"REPLY    {ai['reply_route']} (policy)",
        f"MODE     {ai['response_mode']}",
        f"ACTIONS  {', '.join(str(item) for item in allowed_actions)}",
        f"APPROVERS {', '.join(str(item) for item in approver_roles)}",
        (
            f"TIMEOUT  conversation={ai['conversation_timeout_seconds']}s "
            f"cooldown={ai['response_cooldown_seconds']}s"
        ),
        (
            f"EMERGENCY review={'on' if ai['emergency_detection_enabled'] else 'off'} "
            "/ auto-broadcast=off"
        ),
        "EXEC     Edge/provider adapter required; core never autonomously transmits RF",
    ]


def _confirmed(args: list[str]) -> bool:
    return "--confirm" in args


def _parse_on_off(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"on", "true", "yes", "required", "enable", "enabled"}:
        return True
    if normalized in {"off", "false", "no", "optional", "disable", "disabled"}:
        return False
    raise InvalidConfiguration("activation enforcement must be 'on' or 'off'")


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

    if action in {"enforce", "gate"} and len(args) >= 2:
        ai["activation_required"] = _parse_on_off(args[1])
        ai["activation_position"] = "start"
        updated = await _save(session, organization_id=organization_id, device=device, ai=ai)
        state = "required" if ai["activation_required"] else "off"
        return [f"[ok] {updated.name}: activation gate -> {state}"]

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
        "Usage: edge ai <device> show|bind|unbind|name|agent|trigger|enforce|"
        "provider-channel|frequency|modulation|reply ..."
    )
