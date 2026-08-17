"""Controlled admin commands for TerraListen agents and logical channels."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.errors import InvalidConfiguration
from terrasatch.radio.schemas import AgentCreateRequest, ChannelCreateRequest
from terrasatch.radio.service import create_agent, create_channel, list_agents, list_channels


def _uuid(value: str, label: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidConfiguration(f"{label} must be a UUID") from exc


def _option(args: list[str], name: str) -> str | None:
    if name not in args:
        return None
    index = args.index(name)
    if index + 1 >= len(args):
        raise InvalidConfiguration(f"{name} requires a value")
    return args[index + 1]


async def run_radio_resource_command(
    session: AsyncSession,
    *,
    organization_id: UUID,
    verb: str,
    args: list[str],
) -> list[str]:
    if verb in {"agent", "agents"}:
        if not args or args[0].lower() == "list":
            items = await list_agents(
                session,
                organization_id=organization_id,
                limit=100,
                offset=0,
                enabled=None,
            )
            lines = [
                "ID                                   NAME                     "
                "SITE                                 PROFILE      STATUS"
            ]
            lines.extend(
                f"{item.id}  {item.name[:24]:24} {item.site_id}  "
                f"{item.profile[:12]:12} {'enabled' if item.enabled else 'disabled'}"
                for item in items
            )
            return lines
        if args[0].lower() == "create" and len(args) >= 2:
            site_id = _uuid(args[1], "site_id")
            name = " ".join(args[2:]).strip() or "Satchy"
            item = await create_agent(
                session,
                organization_id=organization_id,
                payload=AgentCreateRequest(
                    name=name,
                    site_id=site_id,
                    profile="terralisten",
                ),
            )
            return [
                f"[ok] agent created -> {item.name} ({item.id})",
                f"profile -> {item.profile}",
            ]
        raise InvalidConfiguration("Usage: agent list | agent create <site_uuid> [name]")

    if verb in {"channel", "channels"}:
        if not args or args[0].lower() == "list":
            items = await list_channels(
                session,
                organization_id=organization_id,
                limit=100,
                offset=0,
                enabled=None,
            )
            lines = [
                "ID                                   NAME                     "
                "SITE                                 AGENT                                STATUS"
            ]
            lines.extend(
                f"{item.id}  {item.name[:24]:24} {item.site_id}  "
                f"{str(item.agent_id or '—')[:36]:36} "
                f"{'enabled' if item.enabled else 'disabled'}"
                for item in items
            )
            return lines
        if args[0].lower() == "create" and len(args) >= 2:
            site_id = _uuid(args[1], "site_id")
            agent_value = _option(args, "--agent")
            agent_id = _uuid(agent_value, "agent_id") if agent_value else None
            name_parts: list[str] = []
            index = 2
            while index < len(args):
                if args[index] == "--agent":
                    index += 2
                    continue
                name_parts.append(args[index])
                index += 1
            name = " ".join(name_parts).strip() or "Satchy AI Channel"
            item = await create_channel(
                session,
                organization_id=organization_id,
                payload=ChannelCreateRequest(
                    name=name,
                    site_id=site_id,
                    agent_id=agent_id,
                    profile="terralisten",
                ),
            )
            return [
                f"[ok] channel created -> {item.name} ({item.id})",
                f"profile -> {item.profile}",
            ]
        raise InvalidConfiguration(
            "Usage: channel list | channel create <site_uuid> [name] "
            "[--agent <agent_uuid>]"
        )

    raise InvalidConfiguration("Unsupported radio resource command")
