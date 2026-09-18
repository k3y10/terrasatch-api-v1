"""TerraSatch self-service billing, activation, and Stripe webhook endpoints."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
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
from terrasatch.config import Environment, Settings
from terrasatch.database.session import create_session_factory
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable

router = APIRouter(prefix="/billing", tags=["billing"])
staging_router = APIRouter(prefix="/workspace/billing", tags=["billing"])
Result = TypeVar("Result")


async def _run_database[Result](
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
            detail=(
                "Checkout is completed or expiring. "
                "Check its status or wait for expiry before retrying."
            ),
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


async def _verified_stripe_event(
    *,
    settings: Settings,
    stripe: StripeGateway,
    raw_payload: bytes,
    stripe_signature: str | None,
) -> tuple[dict[str, object], bytes]:
    """Verify Stripe input with HMAC, or by test-event retrieval in staging only."""

    if stripe_signature and settings.stripe_webhook_secret is not None:
        event = stripe.construct_event(payload=raw_payload, signature=stripe_signature)
        return event, raw_payload

    if settings.environment != Environment.STAGING or settings.billing_allow_livemode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe-Signature header required",
        )
    if not stripe.secret_key.startswith(("sk_test_", "rk_test_")):
        raise ProviderUnavailable("Staging webhook verification requires a Stripe test key")

    try:
        untrusted = json.loads(raw_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidConfiguration("Stripe webhook payload is invalid JSON") from error
    if not isinstance(untrusted, dict):
        raise InvalidConfiguration("Stripe webhook payload is invalid")
    event_id = str(untrusted.get("id") or "")
    event = await stripe.retrieve_event(event_id)
    if bool(event.get("livemode", False)):
        raise ProviderUnavailable("Live Stripe events are disabled in staging")

    verified_payload = json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return event, verified_payload


async def _process_stripe_webhook(
    request: Request,
    stripe_signature: str | None,
) -> WebhookResponse:
    settings: Settings = request.app.state.settings

    if (
        not stripe_signature
        and (
            settings.environment != Environment.STAGING
            or settings.stripe_webhook_secret is not None
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe-Signature header required",
        )

    stripe = _gateway(settings)
    raw_payload = await request.body()
    event, verified_payload = await _verified_stripe_event(
        settings=settings,
        stripe=stripe,
        raw_payload=raw_payload,
        stripe_signature=stripe_signature,
    )
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
                raw_payload=verified_payload,
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


@router.post("/stripe/webhook", response_model=WebhookResponse)
async def post_stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> WebhookResponse:
    """Verify and apply Stripe lifecycle events with transactional email retry safety."""

    return await _process_stripe_webhook(request, stripe_signature)


@staging_router.get("/checkout/status", response_model=CheckoutStatusResponse)
async def get_staging_billing_checkout_status(
    request: Request,
    session_id: Annotated[str, Query(min_length=10, max_length=255)],
) -> CheckoutStatusResponse:
    """Staging alias for polling committed Checkout/webhook provisioning state."""

    return await get_billing_checkout_status(request=request, session_id=session_id)


@staging_router.post("/activate", response_model=ActivationResponse)
async def post_staging_billing_activation(
    payload: ActivationRequest,
    request: Request,
) -> ActivationResponse:
    """Staging alias for consuming the same single-use activation token."""

    return await post_billing_activation(payload=payload, request=request)


@staging_router.get("/success", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_success() -> HTMLResponse:
    """Render a self-contained staging success page without Vercel preview access."""

    return HTMLResponse(
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TerraSatch staging checkout</title></head>
<body style="font-family:system-ui;max-width:760px;margin:64px auto;padding:0 24px">
<h1>TerraSatch staging checkout</h1>
<p id="status">Confirming subscription provisioning…</p>
<script>
const id = new URLSearchParams(location.search).get("session_id");
const target = document.getElementById("status");
async function check() {
  if (!id) { target.textContent = "Missing Checkout session ID."; return; }
  const response = await fetch(
    "/api/v1/workspace/billing/checkout/status?session_id=" + encodeURIComponent(id),
    {credentials: "same-origin"}
  );
  if (!response.ok) {
    target.textContent = "Checkout returned, but provisioning is not confirmed yet.";
    return;
  }
  const data = await response.json();
  target.textContent = data.provisioned
    ? "Subscription webhook processed. Account provisioning is complete."
    : "Checkout returned. Waiting for the Stripe webhook to finish provisioning.";
  if (!data.provisioned) setTimeout(check, 1500);
}
check();
</script></body></html>"""
    )


@staging_router.get("/cancel", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_cancel() -> HTMLResponse:
    """Render a staging Checkout cancellation landing page."""

    return HTMLResponse(
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TerraSatch staging checkout</title></head>
<body style="font-family:system-ui;max-width:760px;margin:64px auto;padding:0 24px">
<h1>Checkout canceled</h1><p>No subscription change was completed.</p></body></html>"""
    )


@staging_router.get("/portal-return", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_portal_return() -> HTMLResponse:
    """Render a safe return target for Stripe Customer Portal acceptance."""

    return HTMLResponse(
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TerraSatch staging billing</title></head>
<body style="font-family:system-ui;max-width:760px;margin:64px auto;padding:0 24px">
<h1>Billing settings updated</h1>
<p>You can close this staging page and continue the acceptance run.</p></body></html>"""
    )


@staging_router.get("/activate", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_activation() -> HTMLResponse:
    """Render a minimal staging-only activation form using the token URL fragment."""

    return HTMLResponse(
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Activate TerraSatch staging account</title></head>
<body style="font-family:system-ui;max-width:760px;margin:64px auto;padding:0 24px">
<h1>Activate TerraSatch staging account</h1>
<form id="activation">
<label>Password <input id="password" type="password" minlength="12" required></label>
<button type="submit">Activate account</button>
</form>
<p id="result"></p>
<script>
const token = new URLSearchParams(location.hash.slice(1)).get("token");
const form = document.getElementById("activation");
const result = document.getElementById("result");
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!token) { result.textContent = "Activation token is missing."; return; }
  const response = await fetch("/api/v1/workspace/billing/activate", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({token, password: document.getElementById("password").value})
  });
  const data = await response.json();
  result.textContent = response.ok
    ? "Account activated successfully."
    : (data?.error?.message || data?.detail || "Activation failed.");
});
</script></body></html>"""
    )


@staging_router.post("/stripe/webhook", response_model=WebhookResponse)
async def post_staging_stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> WebhookResponse:
    """Staging-only alias for the externally exposed isolated workspace host."""

    return await _process_stripe_webhook(request, stripe_signature)
