"""Tenant-safe context resolution for Satchy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.billing.service import get_subscription_for_organization
from terrasatch.config import Settings
from terrasatch.edge.models import EdgeDevice
from terrasatch.errors import ResourceNotFound, TenantAccessDenied
from terrasatch.identity.access import role_allows
from terrasatch.identity.models import Membership, MembershipRole, Organization, Site, Team, User
from terrasatch.integrations.catalog import provider_catalog
from terrasatch.integrations.models import IntegrationStatus
from terrasatch.integrations.service import list_visible_connections
from terrasatch.organizations.profiles import get_operational_profile
from terrasatch.radio.models import (
    Callsign,
    OperationalEvent,
    RadioConversation,
    Transcript,
    Transmission,
)
from terrasatch.workspace.convergence import (
    build_capability_manifest,
    get_workspace_profile,
    workspace_profile_payload,
)
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
    settings: Settings | None = None,
) -> SatchyContext:
    """Build the smallest useful context while enforcing tenant/site ownership."""

    organization = await session.scalar(
        select(Organization).where(
            Organization.id == organization_id,
            Organization.enabled.is_(True),
        )
    )
    if organization is None:
        raise ResourceNotFound("Organization was not found in the Satchy context")

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
    membership: Membership | None = None
    role: str | None = None
    modules: list[str] = []
    user_preferences: dict[str, object] = {}
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
        user_preferences = (
            dict(preference.satchy_preferences or {}) if preference is not None else {}
        )

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

    devices = list(
        await session.scalars(
            select(EdgeDevice)
            .where(
                EdgeDevice.organization_id == organization_id,
                EdgeDevice.site_id == site_id,
                EdgeDevice.enabled.is_(True),
            )
            .order_by(EdgeDevice.last_seen_at.desc(), EdgeDevice.created_at.desc())
        )
    )
    device = devices[0] if devices else None
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

    subscription = await get_subscription_for_organization(
        session,
        organization_id=organization_id,
    )
    subscription_payload: dict[str, object] = {
        "managed": subscription.managed,
        "plan_code": subscription.plan_code.value if subscription.plan_code else None,
        "billing_interval": (
            subscription.billing_interval.value
            if subscription.billing_interval
            else None
        ),
        "status": subscription.status,
        "service_access": subscription.service_access,
        "trial_ends_at": (
            subscription.trial_ends_at.isoformat()
            if subscription.trial_ends_at
            else None
        ),
        "current_period_end": (
            subscription.current_period_end.isoformat()
            if subscription.current_period_end
            else None
        ),
        "entitlements": (
            subscription.entitlements.model_dump()
            if subscription.entitlements is not None
            else None
        ),
    }

    available_capabilities: set[str] = set()
    connected_providers: list[str] = []
    catalog: list[dict[str, object]] = []
    if settings is not None and user is not None and membership is not None:
        connections = await list_visible_connections(
            session,
            organization_id=organization_id,
            user_id=user.id,
            role=membership.role,
        )
        connected_scopes: dict[str, set[str]] = {}
        for connection in connections:
            if (
                connection.enabled
                and connection.status == IntegrationStatus.CONNECTED.value
            ):
                connected_scopes.setdefault(connection.provider, set()).add(
                    connection.scope_type
                )
        catalog = provider_catalog(
            settings,
            admin_access=role_allows(membership.role, MembershipRole.ADMIN),
            connected_scopes=connected_scopes,
        )
        for provider in catalog:
            if provider["connected"] and provider["runtime_ready"]:
                connected_providers.append(provider["key"])
                available_capabilities.update(provider["capabilities"])

    convergence_profile = await get_workspace_profile(
        session,
        organization_id=organization_id,
    )
    capability_manifest = build_capability_manifest(
        profile=convergence_profile,
        catalog=catalog,
        devices=devices,
    )

    return SatchyContext(
        organization_id=organization_id,
        organization_name=organization.name,
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
        callsign=(
            callsign.name
            if callsign
            else (transmission.speaker_text if transmission else None)
        ),
        objective=objective,
        active_map=active_map,
        workspace_modules=modules,
        user_preferences=user_preferences,
        subscription=subscription_payload,
        available_capabilities=sorted(available_capabilities),
        connected_providers=sorted(connected_providers),
        workspace_profile=workspace_profile_payload(convergence_profile),
        capability_manifest=capability_manifest,
        operational_profile=profile_payload,
        edge_context=edge_context,
        rf_context=dict(transmission.rf_metadata or {}) if transmission else {},
        evidence=evidence,
    )