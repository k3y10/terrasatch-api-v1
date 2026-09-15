"""Server-side TerraSatch plan enforcement for newly created resources."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.billing.service import get_subscription_for_organization
from terrasatch.edge.models import EdgeDevice
from terrasatch.errors import ResourceConflict
from terrasatch.identity.models import Membership, Site
from terrasatch.radio.models import Channel


def _limit_error(*, resource: str, current: int, limit: int, plan: str | None) -> ResourceConflict:
    return ResourceConflict(
        f"The TerraSatch {plan or 'subscription'} plan has reached its {resource} limit.",
        details={"resource": resource, "current": current, "limit": limit, "plan": plan},
    )


async def _managed_entitlements(session: AsyncSession, organization_id: UUID):
    subscription = await get_subscription_for_organization(
        session,
        organization_id=organization_id,
    )
    if not subscription.managed:
        return subscription, None
    if subscription.service_access == "restricted":
        raise ResourceConflict(
            "This TerraSatch subscription is restricted. Existing operational data remains available, but new configuration is paused until billing is resolved.",
            details={
                "billing_status": subscription.status,
                "service_access": subscription.service_access,
            },
        )
    return subscription, subscription.entitlements


async def enforce_site_slot(session: AsyncSession, *, organization_id: UUID) -> None:
    subscription, entitlements = await _managed_entitlements(session, organization_id)
    if entitlements is None or entitlements.max_sites is None:
        return
    current = int(
        await session.scalar(
            select(func.count()).select_from(Site).where(
                Site.organization_id == organization_id,
                Site.enabled.is_(True),
            )
        )
        or 0
    )
    if current >= entitlements.max_sites:
        raise _limit_error(
            resource="active sites",
            current=current,
            limit=entitlements.max_sites,
            plan=subscription.plan_code.value if subscription.plan_code else None,
        )


async def enforce_member_slot(session: AsyncSession, *, organization_id: UUID) -> None:
    subscription, entitlements = await _managed_entitlements(session, organization_id)
    if entitlements is None or entitlements.max_members is None:
        return
    current = int(
        await session.scalar(
            select(func.count()).select_from(Membership).where(
                Membership.organization_id == organization_id,
                Membership.enabled.is_(True),
            )
        )
        or 0
    )
    if current >= entitlements.max_members:
        raise _limit_error(
            resource="members",
            current=current,
            limit=entitlements.max_members,
            plan=subscription.plan_code.value if subscription.plan_code else None,
        )


async def enforce_edge_slot(session: AsyncSession, *, organization_id: UUID) -> None:
    subscription, entitlements = await _managed_entitlements(session, organization_id)
    if entitlements is None or entitlements.max_edge_devices is None:
        return
    current = int(
        await session.scalar(
            select(func.count()).select_from(EdgeDevice).where(
                EdgeDevice.organization_id == organization_id,
                EdgeDevice.enabled.is_(True),
            )
        )
        or 0
    )
    if current >= entitlements.max_edge_devices:
        raise _limit_error(
            resource="Edge devices",
            current=current,
            limit=entitlements.max_edge_devices,
            plan=subscription.plan_code.value if subscription.plan_code else None,
        )


async def enforce_channel_slot(session: AsyncSession, *, organization_id: UUID) -> None:
    subscription, entitlements = await _managed_entitlements(session, organization_id)
    if entitlements is None or entitlements.max_channels is None:
        return
    current = int(
        await session.scalar(
            select(func.count()).select_from(Channel).where(
                Channel.organization_id == organization_id,
                Channel.enabled.is_(True),
            )
        )
        or 0
    )
    if current >= entitlements.max_channels:
        raise _limit_error(
            resource="channels",
            current=current,
            limit=entitlements.max_channels,
            plan=subscription.plan_code.value if subscription.plan_code else None,
        )
