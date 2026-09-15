"""Public, non-sensitive Checkout completion status for browser redirects."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.billing.models import BillingActivation, BillingCustomer, BillingSignup
from terrasatch.billing.plans import BillingInterval, PlanCode, get_plan
from terrasatch.billing.schemas import CheckoutStatusResponse
from terrasatch.billing.service import get_subscription_for_organization
from terrasatch.errors import ResourceNotFound


async def get_checkout_status(
    session: AsyncSession,
    *,
    checkout_session_id: str,
) -> CheckoutStatusResponse:
    """Resolve a Checkout session to customer-safe local provisioning state only."""

    signup = await session.scalar(
        select(BillingSignup).where(
            BillingSignup.stripe_checkout_session_id == checkout_session_id
        )
    )
    if signup is None:
        raise ResourceNotFound("Checkout session was not found")

    plan_code = PlanCode(signup.plan_code)
    billing_interval = BillingInterval(signup.billing_interval)
    plan = get_plan(plan_code)
    recurring_amount = plan.amount_cents(billing_interval)
    if recurring_amount is None:
        raise ResourceNotFound("Checkout plan is no longer available")

    now = datetime.now(UTC)
    expires_at = signup.expires_at
    if expires_at.utcoffset() is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if signup.status != "completed" and expires_at <= now:
        return CheckoutStatusResponse(
            state="expired",
            plan_code=plan_code,
            billing_interval=billing_interval,
            recurring_amount_cents=recurring_amount,
            subscription_status=None,
            service_access=None,
            trial_ends_at=None,
            current_period_end=None,
            activation_required=False,
        )

    if signup.status != "completed" or not signup.stripe_customer_id:
        return CheckoutStatusResponse(
            state="processing",
            plan_code=plan_code,
            billing_interval=billing_interval,
            recurring_amount_cents=recurring_amount,
            subscription_status=None,
            service_access=None,
            trial_ends_at=None,
            current_period_end=None,
            activation_required=False,
        )

    billing_customer = await session.scalar(
        select(BillingCustomer).where(
            BillingCustomer.stripe_customer_id == signup.stripe_customer_id
        )
    )
    if billing_customer is None:
        return CheckoutStatusResponse(
            state="processing",
            plan_code=plan_code,
            billing_interval=billing_interval,
            recurring_amount_cents=recurring_amount,
            subscription_status=None,
            service_access=None,
            trial_ends_at=None,
            current_period_end=None,
            activation_required=False,
        )

    subscription = await get_subscription_for_organization(
        session,
        organization_id=billing_customer.organization_id,
    )
    activation_id = await session.scalar(
        select(BillingActivation.id)
        .where(
            BillingActivation.organization_id == billing_customer.organization_id,
            BillingActivation.consumed_at.is_(None),
            BillingActivation.expires_at > now,
        )
        .limit(1)
    )
    return CheckoutStatusResponse(
        state="ready",
        plan_code=plan_code,
        billing_interval=billing_interval,
        recurring_amount_cents=recurring_amount,
        subscription_status=subscription.status,
        service_access=subscription.service_access,
        trial_ends_at=subscription.trial_ends_at,
        current_period_end=subscription.current_period_end,
        activation_required=activation_id is not None,
    )
