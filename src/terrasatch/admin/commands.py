"""Controlled TerraSatch admin commands for the browser operator console.

This is intentionally not a shell. Every command maps to an explicit service-layer
operation with tenant checks and capability gates.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.api.schemas import SiteUpdateRequest
from terrasatch.auth.service import list_api_keys, revoke_api_key
from terrasatch.edge.models import EdgeDevice
from terrasatch.edge.schemas import EdgeDeviceUpdateRequest
from terrasatch.edge.service import get_device, list_devices, update_device
from terrasatch.errors import InvalidConfiguration, ResourceConflict, ResourceNotFound
from terrasatch.identity.models import Organization
from terrasatch.organizations.service import (
    create_site,
    list_organizations,
    list_sites,
    resolve_organization,
    slugify,
    update_site,
)

_RX_CAPABILITIES = {
    "radio:receive",
    "radio:rx",
    "rx",
    "receive",
    "rtl-sdr",
    "rtl",
    "nooelec",
}
_TX_CAPABILITIES = {
    "radio:transmit",
    "radio:tx",
    "tx",
    "transmit",
    "ptt",
}


@dataclass(frozen=True, slots=True)
class AdminCommandResult:
    lines: list[str]
    redirect: str | None = None


def _confirmed(parts: list[str]) -> bool:
    return "--confirm" in parts


def _require_confirmation(parts: list[str], description: str) -> None:
    if not _confirmed(parts):
        raise InvalidConfiguration(
            f"Confirmation required: rerun with --confirm to {description}."
        )


def _uuid(value: str, label: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidConfiguration(f"{label} must be a UUID") from exc


def device_supports_receive(device: EdgeDevice) -> bool:
    capabilities = {str(item).lower() for item in device.capabilities}
    if capabilities & _RX_CAPABILITIES:
        return True
    inventory = " ".join(str(item).lower() for item in device.hardware_inventory)
    return any(token in inventory for token in ("rtl", "nooelec", "nesdr"))


def device_supports_transmit(device: EdgeDevice) -> bool:
    capabilities = {str(item).lower() for item in device.capabilities}
    return bool(capabilities & _TX_CAPABILITIES)


def radio_config(device: EdgeDevice) -> dict[str, object]:
    config = dict(device.remote_config or {})
    radio = config.get("radio")
    return dict(radio) if isinstance(radio, dict) else {}


def radio_mode(device: EdgeDevice) -> str:
    rx_supported = device_supports_receive(device)
    tx_supported = device_supports_transmit(device)
    radio = radio_config(device)
    rx_enabled = bool(radio.get("receive_enabled", rx_supported)) and rx_supported
    tx_enabled = bool(radio.get("transmit_enabled", False)) and tx_supported
    if rx_enabled and tx_enabled:
        return "RX+TX"
    if tx_enabled:
        return "TX"
    if rx_enabled:
        return "RX"
    return "IDLE"


async def _admin_organization(session: AsyncSession, selector: str) -> Organization:
    try:
        organization_id = UUID(selector)
    except ValueError:
        organization = await session.scalar(
            select(Organization).where(
                (Organization.slug == selector) | (Organization.name == selector)
            )
        )
    else:
        organization = await session.scalar(
            select(Organization).where(Organization.id == organization_id)
        )
    if organization is None:
        raise ResourceNotFound("Organization was not found")
    return organization


async def _update_organization(
    session: AsyncSession,
    *,
    selector: str,
    name: str | None = None,
    enabled: bool | None = None,
) -> Organization:
    organization = await _admin_organization(session, selector)
    if name is not None:
        normalized_name = name.strip()
        new_slug = slugify(normalized_name)
        existing = await session.scalar(
            select(Organization).where(
                Organization.account_id == organization.account_id,
                Organization.slug == new_slug,
                Organization.id != organization.id,
            )
        )
        if existing is not None:
            raise ResourceConflict(f"Organization slug '{new_slug}' already exists")
        organization.name = normalized_name
        organization.slug = new_slug
    if enabled is not None:
        organization.enabled = enabled
    await session.flush()
    return organization


def _device_lines(device: EdgeDevice) -> list[str]:
    rx = "supported" if device_supports_receive(device) else "unavailable"
    tx = "supported" if device_supports_transmit(device) else "unavailable"
    radio = radio_config(device)
    return [
        f"ID       {device.id}",
        f"NAME     {device.name}",
        f"SITE     {device.site_id}",
        f"ENABLED  {device.enabled}",
        f"MODE     {radio_mode(device)}",
        f"RX       {rx} / configured={radio.get('receive_enabled', 'auto')}",
        f"TX       {tx} / configured={radio.get('transmit_enabled', False)}",
        f"CAPS     {', '.join(device.capabilities) if device.capabilities else 'none reported'}",
    ]


async def run_admin_command(
    session: AsyncSession,
    *,
    command: str,
    selected_organization: str | None,
) -> AdminCommandResult:
    """Run one allow-listed admin command and return terminal-friendly output."""

    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise InvalidConfiguration(str(exc)) from exc
    if not parts:
        return AdminCommandResult([])

    verb = parts[0].lower()
    args = parts[1:]

    if verb == "help":
        return AdminCommandResult(
            [
                "commands:",
                "  org list | org select <id|slug> | org rename <id|slug> <name>",
                "  org enable|disable <id|slug> [--confirm]",
                "  site list | site create <name> | site rename <uuid> <name>",
                "  site enable|disable <uuid> [--confirm]",
                "  edge list | edge show <uuid> | edge rename <uuid> <name>",
                "  edge enable|disable <uuid> [--confirm]",
                "  edge rx <uuid> on|off | edge tx <uuid> on|off [--confirm]",
                "  key list | key revoke <uuid> --confirm",
                "  docs | clear | logout",
            ]
        )

    if verb in {"org", "organization", "organizations"}:
        if not args or args[0] == "list":
            organizations = await list_organizations(session)
            lines = ["ID                                   NAME                     SLUG             STATUS"]
            lines.extend(
                f"{org.id}  {org.name[:24]:24} {org.slug[:16]:16} {'enabled' if org.enabled else 'disabled'}"
                for org in organizations
            )
            return AdminCommandResult(lines)
        action = args[0].lower()
        if action == "select" and len(args) >= 2:
            organization = await resolve_organization(session, args[1])
            return AdminCommandResult(
                [f"context -> {organization.name} ({organization.slug})"],
                redirect=f"/admin?organization={organization.id}",
            )
        if action == "rename" and len(args) >= 3:
            organization = await _update_organization(
                session, selector=args[1], name=" ".join(args[2:])
            )
            return AdminCommandResult(
                [f"[ok] organization renamed -> {organization.name} ({organization.slug})"],
                redirect=f"/admin?organization={organization.id}",
            )
        if action in {"enable", "disable"} and len(args) >= 2:
            if action == "disable":
                _require_confirmation(parts, f"disable organization {args[1]}")
            organization = await _update_organization(
                session, selector=args[1], enabled=action == "enable"
            )
            return AdminCommandResult(
                [f"[ok] organization {organization.name}: {'enabled' if organization.enabled else 'disabled'}"]
            )
        raise InvalidConfiguration("Usage: org list|select|rename|enable|disable ...")

    if verb in {"site", "sites"}:
        if not selected_organization:
            raise InvalidConfiguration("Select an organization first with: org select <id|slug>")
        organization = await resolve_organization(session, selected_organization)
        if not args or args[0] == "list":
            _, sites = await list_sites(
                session,
                organization_selector=str(organization.id),
                enabled=None,
            )
            lines = ["ID                                   NAME                     STATUS"]
            lines.extend(
                f"{site.id}  {site.name[:24]:24} {'enabled' if site.enabled else 'disabled'}"
                for site in sites
            )
            return AdminCommandResult(lines)
        action = args[0].lower()
        if action == "create" and len(args) >= 2:
            site = await create_site(
                session,
                name=" ".join(args[1:]),
                organization_selector=str(organization.id),
            )
            return AdminCommandResult([f"[ok] site created -> {site.name} ({site.id})"])
        if action == "rename" and len(args) >= 3:
            site = await update_site(
                session,
                organization_id=organization.id,
                site_id=_uuid(args[1], "site_id"),
                payload=SiteUpdateRequest(name=" ".join(args[2:])),
            )
            return AdminCommandResult([f"[ok] site renamed -> {site.name}"])
        if action in {"enable", "disable"} and len(args) >= 2:
            if action == "disable":
                _require_confirmation(parts, f"disable site {args[1]}")
            site = await update_site(
                session,
                organization_id=organization.id,
                site_id=_uuid(args[1], "site_id"),
                payload=SiteUpdateRequest(enabled=action == "enable"),
            )
            return AdminCommandResult(
                [f"[ok] site {site.name}: {'enabled' if site.enabled else 'disabled'}"]
            )
        raise InvalidConfiguration("Usage: site list|create|rename|enable|disable ...")

    if verb in {"edge", "device", "devices"}:
        if not selected_organization:
            raise InvalidConfiguration("Select an organization first with: org select <id|slug>")
        organization = await resolve_organization(session, selected_organization)
        if not args or args[0] == "list":
            devices = await list_devices(session, organization_id=organization.id)
            lines = ["ID                                   NAME                     MODE   STATUS"]
            lines.extend(
                f"{device.id}  {device.name[:24]:24} {radio_mode(device):6} {'enabled' if device.enabled else 'disabled'}"
                for device in devices
            )
            return AdminCommandResult(lines)
        action = args[0].lower()
        if action == "show" and len(args) >= 2:
            device = await get_device(
                session,
                organization_id=organization.id,
                device_id=_uuid(args[1], "device_id"),
            )
            return AdminCommandResult(_device_lines(device))
        if action == "rename" and len(args) >= 3:
            device = await update_device(
                session,
                organization_id=organization.id,
                device_id=_uuid(args[1], "device_id"),
                payload=EdgeDeviceUpdateRequest(name=" ".join(args[2:])),
            )
            return AdminCommandResult([f"[ok] edge renamed -> {device.name}"])
        if action in {"enable", "disable"} and len(args) >= 2:
            if action == "disable":
                _require_confirmation(parts, f"disable edge device {args[1]}")
            device = await update_device(
                session,
                organization_id=organization.id,
                device_id=_uuid(args[1], "device_id"),
                payload=EdgeDeviceUpdateRequest(enabled=action == "enable"),
            )
            return AdminCommandResult(
                [f"[ok] edge {device.name}: {'enabled' if device.enabled else 'disabled'}"]
            )
        if action in {"rx", "tx"} and len(args) >= 3:
            device_id = _uuid(args[1], "device_id")
            state = args[2].lower()
            if state not in {"on", "off"}:
                raise InvalidConfiguration("Radio state must be on or off")
            device = await get_device(
                session,
                organization_id=organization.id,
                device_id=device_id,
            )
            enable = state == "on"
            if action == "rx" and enable and not device_supports_receive(device):
                raise InvalidConfiguration(
                    "Receive unavailable: this Edge device has not reported a receive-capable provider."
                )
            if action == "tx" and enable:
                if not device_supports_transmit(device):
                    raise InvalidConfiguration(
                        "Transmit unavailable: this Edge device has not reported a TX-capable provider/adapter."
                    )
                _require_confirmation(parts, f"enable transmit for edge device {device.id}")
            config = dict(device.remote_config or {})
            radio = radio_config(device)
            radio[f"{'receive' if action == 'rx' else 'transmit'}_enabled"] = enable
            if action == "tx":
                radio["transmit_requires_operator_confirmation"] = True
            config["radio"] = radio
            device = await update_device(
                session,
                organization_id=organization.id,
                device_id=device.id,
                payload=EdgeDeviceUpdateRequest(remote_config=config),
            )
            return AdminCommandResult(
                [
                    f"[ok] {device.name}: {action.upper()} {'enabled' if enable else 'disabled'}",
                    f"mode -> {radio_mode(device)}",
                ]
            )
        raise InvalidConfiguration("Usage: edge list|show|rename|enable|disable|rx|tx ...")

    if verb in {"key", "keys"}:
        if not selected_organization:
            raise InvalidConfiguration("Select an organization first with: org select <id|slug>")
        if not args or args[0] == "list":
            keys = await list_api_keys(
                session,
                organization_selector=selected_organization,
            )
            lines = ["ID                                   NAME                     PREFIX       STATUS"]
            lines.extend(
                f"{key.id}  {key.name[:24]:24} {key.key_prefix[:12]:12} {'revoked' if key.revoked_at else 'active'}"
                for key in keys
            )
            return AdminCommandResult(lines)
        if args[0].lower() == "revoke" and len(args) >= 2:
            _require_confirmation(parts, f"revoke API key {args[1]}")
            key = await revoke_api_key(
                session,
                api_key_id=_uuid(args[1], "api_key_id"),
                organization_selector=selected_organization,
            )
            return AdminCommandResult([f"[ok] API key revoked -> {key.name} ({key.key_prefix})"])
        raise InvalidConfiguration("Usage: key list | key revoke <uuid> --confirm")

    raise InvalidConfiguration(f"command not found: {verb}. type 'help'.")
