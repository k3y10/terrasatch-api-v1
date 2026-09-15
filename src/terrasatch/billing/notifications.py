"""Secure server-to-server delivery of TerraSatch billing email requests to Vercel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.billing.models import Subscription
from terrasatch.billing.plans import BillingInterval, PlanCode, get_plan
from terrasatch.config import Settings
from terrasatch.errors import ProviderUnavailable
from terrasatch.identity.models import Membership, MembershipRole, Organization, User


@dataclass(frozen=True, slots=True)
class BillingEmailContext:
    to: str
    display_name: str
    organization_name: str
    plan_name: str | None
    billing_interval: str | None
    recurring_amount_cents: int | None
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    grace_ends_at: datetime | None
    cancel_at_period_end: bool


async def get_billing_email_context(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> BillingEmailContext | None:
    row = (
        await session.execute(
            select(Organization, User)
            .join(Membership, Membership.organization_id == Organization.id)
            .join(User, User.id == Membership.user_id)
            .where(
                Organization.id == organization_id,
                Membership.role == MembershipRole.OWNER,
                Membership.enabled.is_(True),
                User.enabled.is_(True),
            )
            .order_by(User.created_at)
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    organization, user = row
    subscription = await session.scalar(
        select(Subscription).where(Subscription.organization_id == organization_id)
    )

    plan_name: str | None = None
    interval: str | None = None
    recurring_amount: int | None = None
    if subscription is not None:
        try:
            plan_code = PlanCode(subscription.plan_code)
            billing_interval = BillingInterval(subscription.billing_interval)
            plan = get_plan(plan_code)
            plan_name = plan.name
            interval = billing_interval.value
            recurring_amount = plan.amount_cents(billing_interval)
        except ValueError:
            pass

    return BillingEmailContext(
        to=user.email,
        display_name=user.display_name,
        organization_name=organization.name,
        plan_name=plan_name,
        billing_interval=interval,
        recurring_amount_cents=recurring_amount,
        trial_ends_at=subscription.trial_ends_at if subscription is not None else None,
        current_period_end=subscription.current_period_end if subscription is not None else None,
        grace_ends_at=subscription.grace_ends_at if subscription is not None else None,
        cancel_at_period_end=subscription.cancel_at_period_end if subscription is not None else False,
    )


def notification_kind(
    *,
    stripe_event_type: str,
    activation_token: str | None,
    context: BillingEmailContext | None,
) -> str | None:
    if activation_token:
        return "trial_started"
    if stripe_event_type == "customer.subscription.trial_will_end":
        return "trial_ending"
    if stripe_event_type == "invoice.payment_failed":
        return "payment_failed"
    if stripe_event_type == "customer.subscription.deleted":
        return "subscription_ended"
    if (
        stripe_event_type == "customer.subscription.updated"
        and context is not None
        and context.cancel_at_period_end
    ):
        return "cancellation_scheduled"
    return None


async def deliver_billing_email(
    *,
    settings: Settings,
    event_id: str,
    kind: str,
    context: BillingEmailContext,
    activation_token: str | None = None,
) -> bool:
    """Ask the protected Vercel endpoint to send one idempotent Resend email."""

    if settings.billing_email_webhook_url is None or settings.billing_email_webhook_secret is None:
        return False

    activation_url = None
    if activation_token:
        base_url = str(settings.billing_activation_url).split("#", 1)[0]
        activation_url = f"{base_url}#token={quote(activation_token, safe='')}"

    payload = {
        "eventId": event_id,
        "kind": kind,
        "to": context.to,
        "displayName": context.display_name,
        "organizationName": context.organization_name,
        "planName": context.plan_name,
        "billingInterval": context.billing_interval,
        "recurringAmountCents": context.recurring_amount_cents,
        "trialEndsAt": context.trial_ends_at.isoformat() if context.trial_ends_at else None,
        "currentPeriodEnd": context.current_period_end.isoformat()
        if context.current_period_end
        else None,
        "graceEndsAt": context.grace_ends_at.isoformat() if context.grace_ends_at else None,
        "activationUrl": activation_url,
    }
    headers = {
        "Authorization": f"Bearer {settings.billing_email_webhook_secret.get_secret_value()}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                str(settings.billing_email_webhook_url),
                headers=headers,
                json=payload,
            )
        response.raise_for_status()
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderUnavailable("TerraSatch billing email delivery failed") from error
    return True
