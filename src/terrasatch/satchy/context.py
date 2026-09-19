"""Tenant-safe context resolution for Satchy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.edge.models import EdgeDevice
from terrasatch.errors import ResourceNotFound, TenantAccessDenied
from terrasatch.identity.models import Membership, Site, Team, User
from terrasatch.organizations.profiles import get_operational_profile
from terrasatch.radio.models import Callsign, OperationalEvent, RadioConversation, Transcript, Transmission
from terrasatch.workspace.models import WorkspacePreference

from .schemas import ActiveMapContext, SatchyContext


async def build_satchy_context(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
    user_id: UUID | None = None,
    team_id: UUID | None = None,
    transmission_id: UUID | None = None,
    objective: str | None = None,
    active_map: ActiveMapContext | None = None,
) -> SatchyContext:
    """Build the smallest useful context while enforcing tenant/site ownership."""

    site = await session.scalar(
        select(Site).where(
            Site.id == site_id,
            Site.organization_id == organization_id,
            Site.enabled.is_(True),
        )
    )
    if site is None:
        raise ResourceNotFound("Site was not found in the Satchy organization context")

    user: User | None = None
    role: str | None = None
    modules: list[str] = []
    if user_id is not None:
        membership = await session.scalar(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.enabled.is_(True),
            )
        )
        if membership is None:
            raise TenantAccessDenied("User is not a member of the Satchy organization context")
        user = await session.get(User, user_id)
        if user is None or not user.enabled:
            raise TenantAccessDenied("Satchy user is not enabled")
        role = membership.role.value
        preference = await session.get(WorkspacePreference, (organization_id, user_id))
        modules = list(preference.modules) if preference is not None else []

    transmission: Transmission | None = None
    transcript: Transcript | None = None
    conversation: RadioConversation | None = None
    callsign: Callsign | None = None
    if transmission_id is not None:
        transmission = await session.scalar(
            select(Transmission).where(
                Transmission.id == transmission_id,
                Transmission.organization_id == organization_id,
                Transmission.site_id == site_id,
            )
        )
        if transmission is None:
            raise ResourceNotFound("Transmission was not found in the Satchy context")
        transcript = await session.scalar(
            select(Transcript).where(
                Transcript.organization_id == organization_id,
                Transcript.transmission_id == transmission.id,
            )
        )
        if transmission.conversation_id is not None:
            conversation = await session.scalar(
                select(RadioConversation).where(
                    RadioConversation.id == transmission.conversation_id,
                    RadioConversation.organization_id == organization_id,
                    RadioConversation.site_id == site_id,
                )
            )
        if transmission.speaker_callsign_id is not None:
            callsign = await session.scalar(
                select(Callsign).where(
                    Callsign.id == transmission.speaker_callsign_id,
                    Callsign.organization_id == organization_id,
                )
            )
            if team_id is None and callsign is not None:
                team_id = callsign.team_id

    team: Team | None = None
    if team_id is not None:
        team = await session.scalar(
            select(Team).where(
                Team.id == team_id,
                Team.organization_id == organization_id,
                Team.enabled.is_(True),
                or_(Team.site_id == site_id, Team.site_id.is_(None)),
            )
        )
        if team is None:
            raise TenantAccessDenied("Team is outside the Satchy site context")

    profile = await get_operational_profile(
        session,
        organization_id=organization_id,
        site_id=site_id,
    )
    profile_payload: dict[str, object] = {}
    if profile is not None:
        profile_payload = {
            "industry": profile.industry,
            "operation_type": profile.operation_type,
            "teams": profile.teams,
            "roles": profile.roles,
            "callsigns": profile.callsigns,
            "radio_protocol": profile.radio_protocol,
            "terminology": profile.terminology,
            "location_aliases": profile.location_aliases,
            "event_types": profile.event_types,
            "emergency_terms": profile.emergency_terms,
        }

    device = await session.scalar(
        select(EdgeDevice)
        .where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.site_id == site_id,
            EdgeDevice.enabled.is_(True),
        )
        .order_by(EdgeDevice.last_seen_at.desc(), EdgeDevice.created_at.desc())
        .limit(1)
    )
    edge_context: dict[str, object] = {}
    if device is not None:
        edge_context = {
            "device_id": str(device.id),
            "name": device.name,
            "capabilities": list(device.capabilities or []),
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        }

    event_query = (
        select(OperationalEvent)
        .join(Transmission, Transmission.id == OperationalEvent.transmission_id)
        .where(
            OperationalEvent.organization_id == organization_id,
            OperationalEvent.site_id == site_id,
            Transmission.organization_id == organization_id,
            Transmission.site_id == site_id,
        )
    )
    if conversation is not None:
        event_query = event_query.where(Transmission.conversation_id == conversation.id)
    elif transmission is not None:
        event_query = event_query.where(OperationalEvent.transmission_id == transmission.id)
    events = list(
        await session.scalars(event_query.order_by(OperationalEvent.created_at.desc()).limit(16))
    )
    evidence = [
        {
            "id": str(event.id),
            "transmission_id": str(event.transmission_id),
            "type": event.event_type,
            "summary": event.summary,
            "callsign": event.callsign,
            "location": event.location_text,
            "confidence": event.confidence,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        for event in reversed(events)
    ]
    if transmission is not None and transcript is not None:
        evidence.append(
            {
                "id": str(transmission.id),
                "type": "source_transmission",
                "summary": transcript.raw_text,
                "callsign": transmission.speaker_text,
                "location": transmission.rf_metadata.get("reported_location"),
                "created_at": transmission.received_at.isoformat(),
            }
        )

    return SatchyContext(
        organization_id=organization_id,
        site_id=site_id,
        site_name=site.name,
        user_id=user.id if user else None,
        user_name=user.display_name if user else None,
        membership_role=role,
        team_id=team.id if team else None,
        team_name=team.name if team else None,
        transmission_id=transmission.id if transmission else None,
        conversation_id=conversation.id if conversation else None,
        channel_id=transmission.channel_id if transmission else None,
        callsign=callsign.name if callsign else (transmission.speaker_text if transmission else None),
        objective=objective,
        active_map=active_map,
        workspace_modules=modules,
        operational_profile=profile_payload,
        edge_context=edge_context,
        rf_context=dict(transmission.rf_metadata or {}) if transmission else {},
        evidence=evidence,
    )
