"""Extended browser-admin command router for Satchy and TerraListen channels."""

from __future__ import annotations

import shlex
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.ai_channel import ai_channel_lines, run_ai_channel_command
from terrasatch.admin.channel_commands import run_radio_resource_command
from terrasatch.admin.commands import AdminCommandResult
from terrasatch.admin.commands import run_admin_command as run_base_admin_command
from terrasatch.edge.service import get_device
from terrasatch.errors import InvalidConfiguration
from terrasatch.masterdata.admin_commands import run_masterdata_command
from terrasatch.organizations.service import resolve_organization


def _uuid(value: str, label: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidConfiguration(f"{label} must be a UUID") from exc


async def run_admin_command(
    session: AsyncSession,
    *,
    command: str,
    selected_organization: str | None,
) -> AdminCommandResult:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise InvalidConfiguration(str(exc)) from exc
    if not parts:
        return AdminCommandResult([])

    verb = parts[0].lower()
    args = parts[1:]

    if verb == "help":
        base = await run_base_admin_command(
            session,
            command=command,
            selected_organization=selected_organization,
        )
        extra = [
            "  agent list | agent create <site_uuid> [name]  (defaults to Satchy)",
            "  channel list | channel create <site_uuid> [name] [--agent <agent_uuid>]",
            "  edge ai <device_uuid> show | bind <channel_uuid> | unbind --confirm",
            "  edge ai <device_uuid> trigger <phrase> | provider-channel <label|off>",
            "  edge ai <device_uuid> frequency <hz|off> | modulation fm|nfm|wbfm|am",
            "  edge ai <device_uuid> reply dashboard|push|tts|rf [--confirm]",
            "  source list | source show <id|slug> | source sync <id|slug>",
            "  sync list | sync <source-id|slug> | inspect [source|event] <id|text>",
            "  database status | backup status",
        ]
        if not base.lines:
            return AdminCommandResult(extra)
        return AdminCommandResult(base.lines[:-1] + extra + base.lines[-1:])

    if verb in {"agent", "agents", "channel", "channels"}:
        if not selected_organization:
            raise InvalidConfiguration("Select an organization first with: org select <id|slug>")
        organization = await resolve_organization(session, selected_organization)
        lines = await run_radio_resource_command(
            session,
            organization_id=organization.id,
            verb=verb,
            args=args,
        )
        return AdminCommandResult(lines)

    masterdata_result = await run_masterdata_command(
        session,
        verb=verb,
        args=args,
        selected_organization=selected_organization,
    )
    if masterdata_result is not None:
        return masterdata_result

    if verb in {"edge", "device", "devices"} and args:
        action = args[0].lower()
        if action in {"ai", "ai-channel"}:
            if not selected_organization:
                raise InvalidConfiguration(
                    "Select an organization first with: org select <id|slug>"
                )
            if len(args) < 2:
                raise InvalidConfiguration(
                    "Usage: edge ai <device_uuid> "
                    "show|bind|trigger|provider-channel|frequency|modulation|reply ..."
                )
            organization = await resolve_organization(session, selected_organization)
            device = await get_device(
                session,
                organization_id=organization.id,
                device_id=_uuid(args[1], "device_id"),
            )
            lines = await run_ai_channel_command(
                session,
                organization_id=organization.id,
                device=device,
                args=args[2:],
            )
            return AdminCommandResult(lines)

        if action == "show" and len(args) >= 2:
            result = await run_base_admin_command(
                session,
                command=command,
                selected_organization=selected_organization,
            )
            if not selected_organization:
                return result
            organization = await resolve_organization(session, selected_organization)
            device = await get_device(
                session,
                organization_id=organization.id,
                device_id=_uuid(args[1], "device_id"),
            )
            return AdminCommandResult(
                result.lines + [""] + ai_channel_lines(device),
                redirect=result.redirect,
            )

    return await run_base_admin_command(
        session,
        command=command,
        selected_organization=selected_organization,
    )
