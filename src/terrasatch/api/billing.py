"""TerraSatch self-service billing, activation, and Stripe webhook endpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.auth.dependencies import Principal, require_any_scope
from terrasatch.billing.notifications import (
    get_billing_email_context,
    notification_kind,
)
from terrasatch.billing.outbox import enqueue_email
from terrasatch.billing.plans import get_plan
from terrasatch.billing.rate_limit import enforce_checkout_rate_limit, enforce_public_rate_limit
from terrasatch.billing.schemas import (
    ActivationRequest,
    ActivationResponse,
    BillingPlanResponse,
    CheckoutRequest,
    CheckoutSessionResponse,
    CheckoutStatusResponse,
    CustomerPortalResponse,
    SubscriptionResponse,
    WebhookResponse,
)
from terrasatch.billing.service import (
    activate_owner,
    create_signup,
    get_stripe_customer_id,
    get_subscription_for_organization,
    mark_checkout_created,
    process_verified_event,
    public_plans,
)
from terrasatch.billing.status import get_checkout_status
from terrasatch.billing.stripe_gateway import StripeGateway
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable

router = APIRouter(prefix="/billing", tags=["billing"])
Result = TypeVar("Result")


async def _run_database(
    settings: Settings,
    operation: Callable[[AsyncSession], Awaitable[Result]],
) -> Result:
    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        try:
            result = await operation(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


def _gateway(settings: Settings) -> StripeGateway:
    return StripeGateway(settings)


@router.get("/plans", response_model=list[BillingPlanResponse])
async def get_billing_plans() -> list[BillingPlanResponse]:
    """Return customer-safe plan and entitlement definitions without Stripe IDs."""

    return [BillingPlanResponse.model_validate(plan) for plan in public_plans()]


@router.post(
    "/checkout",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_billing_checkout(
    payload: CheckoutRequest,
    request: Request,
) -> CheckoutSessionResponse:
    """Create a 30-day subscription trial in Stripe Checkout without trusting price IDs."""

    settings: Settings = request.app.state.settings
    stripe = _gateway(settings)
    if not settings.billing_is_configured:
        raise ProviderUnavailable("Billing activation and email configuration is incomplete")
    plan = get_plan(payload.plan_code)
    recurring_amount = plan.amount_cents(payload.billing_interval)
    if not plan.self_service or recurring_amount is None:
        raise InvalidConfiguration("The selected plan is not available for self-service checkout")

    await enforce_checkout_rate_limit(
        settings,
        client_host=request.client.host if request.client is not None else None,
        email=payload.email,
    )

    # Persist/resume the signup intent before making the external Stripe request.
    # If Stripe succeeds but the later local write fails, a retry reuses this
    # signup ID and therefore the same Stripe idempotency key/session.
    signup = await _run_database(
        settings,
        lambda session: create_signup(session, payload=payload, settings=settings),
    )
    if signup.stripe_checkout_session_id:
        from datetime import UTC, datetime

        existing = await stripe.retrieve_checkout(signup.stripe_checkout_session_id)
        if (
            existing.get("status") == "open"
            and existing.get("url")
            and int(existing.get("expires_at", 0)) > datetime.now(UTC).timestamp() + 60
        ):
            return CheckoutSessionResponse(
                signup_id=signup.id,
                checkout_session_id=existing["id"],
                checkout_url=existing["url"],
                expires_at=datetime.fromtimestamp(existing["expires_at"], UTC),
                plan_code=payload.plan_code,
                billing_interval=payload.billing_interval,
                trial_days=plan.trial_days,
                recurring_amount_cents=recurring_amount,
            )
        raise HTTPException(
            status_code=409,
            detail="Checkout is completed or expiring. Check its status or wait for expiry before retrying.",
        )
    checkout = await stripe.create_checkout(
        signup_id=str(signup.id),
        email=signup.email,
        plan=plan,
        interval=payload.billing_interval,
        expires_at=signup.expires_at,
    )
    await _run_database(
        settings,
        lambda session: mark_checkout_created(
            session,
            signup_id=signup.id,
            checkout_session_id=checkout.session_id,
            checkout_expires_at=checkout.expires_at,
        ),
    )

    return CheckoutSessionResponse(
        signup_id=signup.id,
        checkout_session_id=checkout.session_id,
        checkout_url=checkout.url,
        expires_at=checkout.expires_at,
        plan_code=payload.plan_code,
        billing_interval=payload.billing_interval,
        trial_days=plan.trial_days,
        recurring_amount_cents=recurring_amount,
    )


@router.get("/checkout/status", response_model=CheckoutStatusResponse)
async def get_billing_checkout_status(
    request: Request,
    session_id: Annotated[str, Query(min_length=10, max_length=255)],
) -> CheckoutStatusResponse:
    """Confirm local webhook provisioning after Stripe redirects the browser back."""

    await enforce_public_rate_limit(
        request.app.state.settings,
        category="billing-status",
        identifier=request.client.host if request.client else "unknown",
        limit=120,
    )
    return await _run_database(
        request.app.state.settings,
        lambda session: get_checkout_status(
            session,
            checkout_session_id=session_id,
        ),
    )


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_billing_subscription(
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_any_scope("read:billing", "write:billing")),
    ],
) -> SubscriptionResponse:
    """Return the authenticated organization's TerraSatch subscription and entitlements."""

    return await _run_database(
        request.app.state.settings,
        lambda session: get_subscription_for_organization(
            session,
            organization_id=principal.organization_id,
        ),
    )


@router.post("/portal", response_model=CustomerPortalResponse)
async def post_billing_portal(
    request: Request,
    principal: Annotated[Principal, Depends(require_any_scope("write:billing"))],
) -> CustomerPortalResponse:
    """Create a short-lived Stripe Customer Portal session for this organization."""

    settings: Settings = request.app.state.settings
    customer_id = await _run_database(
        settings,
        lambda session: get_stripe_customer_id(
            session,
            organization_id=principal.organization_id,
        ),
    )
    url = await _gateway(settings).create_customer_portal(stripe_customer_id=customer_id)
    return CustomerPortalResponse(url=url)


@router.post("/activate", response_model=ActivationResponse)
async def post_billing_activation(
    payload: ActivationRequest,
    request: Request,
) -> ActivationResponse:
    """Consume a single-use activation token and set the initial portal password."""

    await enforce_public_rate_limit(
        request.app.state.settings,
        category="activation",
        identifier=request.client.host if request.client else "unknown",
        limit=10,
        window=3600,
    )
    organization_id = await _run_database(
        request.app.state.settings,
        lambda session: activate_owner(
            session,
            token=payload.token,
            password=payload.password,
        ),
    )
    return ActivationResponse(activated=True, organization_id=organization_id)


@router.post("/stripe/webhook", response_model=WebhookResponse)
async def post_stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> WebhookResponse:
    """Verify and apply Stripe lifecycle events with transactional email retry safety."""

    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe-Signature header required",
        )
    settings: Settings = request.app.state.settings
    stripe = _gateway(settings)
    raw_payload = await request.body()
    event = stripe.construct_event(payload=raw_payload, signature=stripe_signature)
    if bool(event.get("livemode", False)) and not settings.billing_allow_livemode:
        raise ProviderUnavailable(
            "Live Stripe events are disabled until TerraSatch explicitly enables live billing"
        )

    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not event_id:
        raise InvalidConfiguration("Stripe webhook event is missing an ID")

    subscription_snapshot = None
    if event_type == "checkout.session.completed":
        data = event.get("data")
        checkout = data.get("object") if isinstance(data, dict) else None
        subscription_id = None
        if isinstance(checkout, dict):
            subscription = checkout.get("subscription")
            if isinstance(subscription, str):
                subscription_id = subscription
            elif isinstance(subscription, dict) and subscription.get("id"):
                subscription_id = str(subscription["id"])
        if not subscription_id:
            raise InvalidConfiguration("Completed Checkout is missing a subscription")
        subscription_snapshot = await stripe.retrieve_subscription(subscription_id)

    session_factory = create_session_factory(settings)
    async with session_factory() as database:
        try:
            result = await process_verified_event(
                database,
                event=event,
                raw_payload=raw_payload,
                settings=settings,
                subscription_snapshot=subscription_snapshot,
            )
            if not result.duplicate and result.organization_id is not None:
                context = await get_billing_email_context(
                    database,
                    organization_id=result.organization_id,
                )
                kind = notification_kind(
                    stripe_event_type=event_type,
                    activation_token=result.activation_token,
                    context=context,
                )
                if context is not None and kind is not None:
                    await enqueue_email(
                        database,
                        event_id=event_id,
                        kind=kind,
                        context=context,
                        activation_token=result.activation_token,
                    )
            await database.commit()
        except Exception:
            await database.rollback()
            raise

    return WebhookResponse(received=True, duplicate=result.duplicate)
