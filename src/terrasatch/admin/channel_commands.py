"""Controlled admin commands for TerraListen agents and logical channels."""
from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from terrasatch.errors import InvalidConfiguration
from terrasatch.radio.schemas import AgentCreateRequest, ChannelCreateRequest
from terrasatch.radio.service import create_agent, create_channel, list_agents, list_channels

def _uuid(value: str, label: str) -> UUID:
    try: return UUID(value)
    except ValueError as exc: raise InvalidConfiguration(f"{label} must be a UUID") from exc

def _option(args: list[str], name: str) -> str | None:
    if name not in args: return None
    i=args.index(name)
    if i+1>=len(args): raise InvalidConfiguration(f"{name} requires a value")
    return args[i+1]

async def run_radio_resource_command(session: AsyncSession, *, organization_id: UUID, verb: str, args: list[str]) -> list[str]:
    if verb in {"agent","agents"}:
        if not args or args[0].lower()=="list":
            items=await list_agents(session,organization_id=organization_id,limit=100,offset=0,enabled=None)
            lines=["ID                                   NAME                     SITE                                 PROFILE      STATUS"]
            lines.extend(f"{x.id}  {x.name[:24]:24} {x.site_id}  {x.profile[:12]:12} {'enabled' if x.enabled else 'disabled'}" for x in items)
            return lines
        if args[0].lower()=="create" and len(args)>=2:
            site_id=_uuid(args[1],"site_id")
            name=" ".join(x for x in args[2:] if not x.startswith("--")).strip() or "Satchy"
            item=await create_agent(session,organization_id=organization_id,payload=AgentCreateRequest(name=name,site_id=site_id,profile="terralisten"))
            return [f"[ok] agent created -> {item.name} ({item.id})",f"profile -> {item.profile}"]
        raise InvalidConfiguration("Usage: agent list | agent create <site_uuid> [name]")
    if verb in {"channel","channels"}:
        if not args or args[0].lower()=="list":
            items=await list_channels(session,organization_id=organization_id,limit=100,offset=0,enabled=None)
            lines=["ID                                   NAME                     SITE                                 AGENT                                STATUS"]
            lines.extend(f"{x.id}  {x.name[:24]:24} {x.site_id}  {str(x.agent_id or '—')[:36]:36} {'enabled' if x.enabled else 'disabled'}" for x in items)
            return lines
        if args[0].lower()=="create" and len(args)>=2:
            site_id=_uuid(args[1],"site_id"); agent_value=_option(args,"--agent"); agent_id=_uuid(agent_value,"agent_id") if agent_value else None
            skip={"--agent"};
            if agent_value: skip.add(agent_value)
            name=" ".join(x for x in args[2:] if x not in skip).strip() or "Satchy AI Channel"
            item=await create_channel(session,organization_id=organization_id,payload=ChannelCreateRequest(name=name,site_id=site_id,agent_id=agent_id,profile="terralisten"))
            return [f"[ok] channel created -> {item.name} ({item.id})",f"profile -> {item.profile}"]
        raise InvalidConfiguration("Usage: channel list | channel create <site_uuid> [name] [--agent <agent_uuid>]")
    raise InvalidConfiguration("Unsupported radio resource command")
