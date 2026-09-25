"""TerraSatch self-service billing, activation, and Stripe webhook endpoints."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, TypeVar
from urllib.parse import urlencode

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
from terrasatch.billing.resend_webhook import (
    reconcile_resend_webhook,
    verify_resend_webhook,
)
from terrasatch.billing.schemas import (
    ActivationRequest,
    ActivationResponse,
    BillingPlanResponse,
    CheckoutRequest,
    CheckoutSessionResponse,
    CheckoutStatusResponse,
    CryptoInvoiceSubscriptionResponse,
    CustomerPortalResponse,
    EmailProviderWebhookResponse,
    SubscriptionResponse,
    WebhookResponse,
)
from terrasatch.billing.service import (
    activate_owner,
    create_signup,
    get_stripe_customer_id,
    get_subscription_for_organization,
    mark_checkout_created,
    mark_invoice_subscription_created,
    process_verified_event,
    public_plans,
    recover_pending_activation_token_for_checkout,
)
from terrasatch.billing.staging_ui import (
    render_staging_billing_activation,
    render_staging_billing_cancel,
    render_staging_billing_portal_return,
    render_staging_billing_success,
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


async def _process_resend_webhook_request(
    request: Request,
) -> EmailProviderWebhookResponse:
    settings: Settings = request.app.state.settings
    if settings.resend_webhook_secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    raw_payload = await request.body()
    if len(raw_payload) > 64_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Webhook payload is too large",
        )
    try:
        event, webhook_id = verify_resend_webhook(
            raw_payload=raw_payload,
            headers=request.headers,
            secret=settings.resend_webhook_secret,
        )
    except InvalidConfiguration as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Resend webhook",
        ) from error

    result = await _run_database(
        settings,
        lambda session: reconcile_resend_webhook(
            session,
            event=event,
            webhook_id=webhook_id,
        ),
    )
    return EmailProviderWebhookResponse(
        matched=result.matched,
        duplicate=result.duplicate,
    )


@router.post("/resend/webhook", response_model=EmailProviderWebhookResponse)
async def post_resend_webhook(request: Request) -> EmailProviderWebhookResponse:
    """Reconcile signed Resend delivery/bounce events with the billing outbox."""

    return await _process_resend_webhook_request(request)


@staging_router.post("/resend/webhook", response_model=EmailProviderWebhookResponse)
async def post_staging_resend_webhook(
    request: Request,
) -> EmailProviderWebhookResponse:
    """Expose the same signed Resend reconciliation route on isolated staging."""

    return await _process_resend_webhook_request(request)


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
    """Create a 14-day subscription trial in Stripe Checkout without trusting price IDs."""

    settings: Settings = request.app.state.settings
    plan = get_plan(payload.plan_code)
    recurring_amount = plan.amount_cents(payload.billing_interval)
    if not plan.self_service or recurring_amount is None:
        raise InvalidConfiguration("The selected plan is not available for self-service checkout")
    if not settings.billing_is_configured:
        raise ProviderUnavailable("Billing activation and provider configuration is incomplete")

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

    if settings.staging_payment_links_are_configured:
        if payload.billing_interval.value != "monthly":
            raise InvalidConfiguration(
                "Staging Payment Link checkout currently supports monthly plans"
            )
        if payload.plan_code.value == "field":
            payment_link_url = settings.billing_staging_individual_payment_link_url
        elif payload.plan_code.value == "team":
            payment_link_url = settings.billing_staging_team_payment_link_url
        else:
            payment_link_url = None
        if not payment_link_url:
            raise ProviderUnavailable("Staging Payment Link checkout is not configured")
        query = urlencode(
            {
                "client_reference_id": str(signup.id),
                "locked_prefilled_email": signup.email,
            }
        )
        separator = "&" if "?" in payment_link_url else "?"
        return CheckoutSessionResponse(
            signup_id=signup.id,
            checkout_session_id=None,
            checkout_url=f"{payment_link_url}{separator}{query}",
            expires_at=signup.expires_at,
            plan_code=payload.plan_code,
            billing_interval=payload.billing_interval,
            trial_days=plan.trial_days,
            recurring_amount_cents=recurring_amount,
        )

    stripe = _gateway(settings)
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


async def _create_crypto_invoice_subscription(
    *,
    payload: CheckoutRequest,
    request: Request,
) -> CryptoInvoiceSubscriptionResponse:
    settings: Settings = request.app.state.settings
    plan = get_plan(payload.plan_code)
    recurring_amount = plan.amount_cents(payload.billing_interval)
    if not plan.self_service or recurring_amount is None:
        raise InvalidConfiguration("The selected plan is not available for self-service billing")
    if not settings.billing_is_configured:
        raise ProviderUnavailable("Billing activation and provider configuration is incomplete")
    if settings.stripe_secret_key is None:
        raise ProviderUnavailable(
            "Crypto invoice subscriptions require a server-side Stripe restricted test key"
        )

    await enforce_checkout_rate_limit(
        settings,
        client_host=request.client.host if request.client is not None else None,
        email=payload.email,
    )
    signup = await _run_database(
        settings,
        lambda session: create_signup(session, payload=payload, settings=settings),
    )
    stripe = _gateway(settings)
    result = await stripe.create_crypto_invoice_subscription(
        signup_id=str(signup.id),
        email=signup.email,
        display_name=signup.display_name,
        plan=plan,
        interval=payload.billing_interval,
        days_until_due=settings.billing_crypto_invoice_days_until_due,
    )
    await _run_database(
        settings,
        lambda session: mark_invoice_subscription_created(
            session,
            signup_id=signup.id,
            stripe_customer_id=result.customer_id,
        ),
    )
    return CryptoInvoiceSubscriptionResponse(
        signup_id=signup.id,
        stripe_subscription_id=result.subscription_id,
        stripe_customer_id=result.customer_id,
        status=result.status,
        plan_code=payload.plan_code,
        billing_interval=payload.billing_interval,
        trial_days=plan.trial_days,
        trial_ends_at=result.trial_end,
        recurring_amount_cents=recurring_amount,
        invoice_payment_window_days=result.days_until_due,
    )


@router.post(
    "/crypto-subscription",
    response_model=CryptoInvoiceSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_crypto_invoice_subscription(
    payload: CheckoutRequest,
    request: Request,
) -> CryptoInvoiceSubscriptionResponse:
    """Create a 14-day send-invoice subscription payable with eligible stablecoins."""

    return await _create_crypto_invoice_subscription(payload=payload, request=request)


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


def _validate_staging_payment_link_event(
    *,
    settings: Settings,
    event: dict[str, object],
) -> None:
    """Validate the strict test-mode Payment Link envelope after Caddy IP allowlisting."""

    if bool(event.get("livemode", False)):
        raise ProviderUnavailable("Live Stripe events are disabled in staging")
    event_type = str(event.get("type") or "")
    allowed = {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.trial_will_end",
        "invoice.paid",
        "invoice.payment_failed",
    }
    if event_type not in allowed:
        raise InvalidConfiguration("Stripe event type is not enabled for TerraSatch staging")

    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        raise InvalidConfiguration("Stripe webhook event is missing its data object")

    if event_type == "checkout.session.completed":
        payment_link = str(obj.get("payment_link") or "")
        expected_links = {
            str(settings.billing_staging_individual_payment_link_id): "field",
            str(settings.billing_staging_team_payment_link_id): "team",
        }
        expected_plan = expected_links.get(payment_link)
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        if (
            expected_plan is None
            or obj.get("mode") != "subscription"
            or not obj.get("client_reference_id")
            or str(metadata.get("product") or "") != "terrasatch"
            or str(metadata.get("billing_version") or "") != "v2"
            or str(metadata.get("environment") or "") != "staging"
            or str(metadata.get("plan_code") or "") != expected_plan
            or str(metadata.get("billing_interval") or "") != "monthly"
        ):
            raise InvalidConfiguration(
                "Checkout Session is not an approved TerraSatch staging Payment Link"
            )

    if event_type.startswith("customer.subscription."):
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        if (
            str(metadata.get("product") or "") != "terrasatch"
            or str(metadata.get("billing_version") or "") != "v2"
            or str(metadata.get("environment") or "") != "staging"
            or str(metadata.get("plan_code") or "") not in {"field", "team"}
            or str(metadata.get("billing_interval") or "") != "monthly"
        ):
            raise InvalidConfiguration("Subscription is not an approved TerraSatch staging record")


async def _verified_stripe_event(
    *,
    settings: Settings,
    stripe: StripeGateway | None,
    raw_payload: bytes,
    stripe_signature: str | None,
) -> tuple[dict[str, object], bytes]:
    """Verify Stripe input with HMAC, or by test-event retrieval in staging only."""

    if stripe_signature and settings.stripe_webhook_secret is not None:
        if stripe is None:
            raise ProviderUnavailable("Stripe verification gateway is unavailable")
        event = stripe.construct_event(payload=raw_payload, signature=stripe_signature)
        return event, raw_payload

    if settings.environment != Environment.STAGING or settings.billing_allow_livemode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe-Signature header required",
        )

    try:
        untrusted = json.loads(raw_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidConfiguration("Stripe webhook payload is invalid JSON") from error
    if not isinstance(untrusted, dict):
        raise InvalidConfiguration("Stripe webhook payload is invalid")

    if stripe is not None and stripe.secret_key.startswith(("sk_test_", "rk_test_")):
        event_id = str(untrusted.get("id") or "")
        event = await stripe.retrieve_event(event_id)
        if bool(event.get("livemode", False)):
            raise ProviderUnavailable("Live Stripe events are disabled in staging")
        _validate_staging_payment_link_event(settings=settings, event=event)
        verified_payload = json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return event, verified_payload

    if settings.staging_payment_links_are_configured:
        _validate_staging_payment_link_event(settings=settings, event=untrusted)
        return untrusted, raw_payload

    raise ProviderUnavailable("Staging webhook verification is not configured")


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

    stripe = _gateway(settings) if settings.stripe_secret_key is not None else None
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
        if stripe is not None:
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
            if (
                not result.duplicate
                and result.state_applied
                and result.organization_id is not None
                and settings.billing_email_is_configured
            ):
                context = await get_billing_email_context(
                    database,
                    organization_id=result.organization_id,
                )
                data = event.get("data")
                previous_attributes = (
                    data.get("previous_attributes")
                    if isinstance(data, dict)
                    and isinstance(data.get("previous_attributes"), dict)
                    else None
                )
                event_object = (
                    data.get("object")
                    if isinstance(data, dict)
                    and isinstance(data.get("object"), dict)
                    else None
                )
                kind = notification_kind(
                    stripe_event_type=event_type,
                    activation_token=result.activation_token,
                    context=context,
                    previous_attributes=previous_attributes,
                    event_object=event_object,
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


@staging_router.get("/plans", response_model=list[BillingPlanResponse])
async def get_staging_billing_plans() -> list[BillingPlanResponse]:
    """Expose customer-safe plan definitions on the isolated staging surface."""

    return await get_billing_plans()


@staging_router.post(
    "/checkout",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_staging_billing_checkout(
    payload: CheckoutRequest,
    request: Request,
) -> CheckoutSessionResponse:
    """Create an isolated staging Checkout using the configured sandbox provider."""

    return await post_billing_checkout(payload=payload, request=request)


@staging_router.post(
    "/crypto-subscription",
    response_model=CryptoInvoiceSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_staging_crypto_invoice_subscription(
    payload: CheckoutRequest,
    request: Request,
) -> CryptoInvoiceSubscriptionResponse:
    """Create a sandbox send-invoice subscription for customer-approved crypto invoices."""

    return await _create_crypto_invoice_subscription(payload=payload, request=request)


@staging_router.get("/checkout/status", response_model=CheckoutStatusResponse)
async def get_staging_billing_checkout_status(
    request: Request,
    session_id: Annotated[str, Query(min_length=10, max_length=255)],
) -> CheckoutStatusResponse:
    """Staging alias for polling committed Checkout/webhook provisioning state."""

    return await get_billing_checkout_status(request=request, session_id=session_id)


@staging_router.get("/checkout/activation")
async def get_staging_checkout_activation(
    request: Request,
    session_id: Annotated[str, Query(min_length=10, max_length=255)],
) -> dict[str, str | None]:
    """Return pending activation context only on the isolated staging surface."""

    settings: Settings = request.app.state.settings
    if settings.environment != Environment.STAGING or settings.billing_allow_livemode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await enforce_public_rate_limit(
        settings,
        category="billing-staging-activation",
        identifier=request.client.host if request.client else "unknown",
        limit=60,
    )
    activation = await _run_database(
        settings,
        lambda session: recover_pending_activation_token_for_checkout(
            session,
            checkout_session_id=session_id,
            settings=settings,
        ),
    )
    if activation is None:
        return {"token": None, "email": None}
    token, email = activation
    return {"token": token, "email": email}


@staging_router.post("/activate", response_model=ActivationResponse)
async def post_staging_billing_activation(
    payload: ActivationRequest,
    request: Request,
) -> ActivationResponse:
    """Staging alias for consuming the same single-use activation token."""

    return await post_billing_activation(payload=payload, request=request)


@staging_router.get("/success", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_success() -> HTMLResponse:
    """Render branded staging onboarding and complete activation inline."""

    return HTMLResponse(
        render_staging_billing_success(),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@staging_router.get("/cancel", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_cancel() -> HTMLResponse:
    """Render a branded staging Checkout cancellation landing page."""

    return HTMLResponse(
        render_staging_billing_cancel(),
        headers={"Cache-Control": "no-store"},
    )


@staging_router.get("/portal-return", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_portal_return() -> HTMLResponse:
    """Render a branded safe return target for Stripe Customer Portal acceptance."""

    return HTMLResponse(
        render_staging_billing_portal_return(),
        headers={"Cache-Control": "no-store"},
    )


@staging_router.get("/activate", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_activation() -> HTMLResponse:
    """Render the branded legacy activation page for emailed staging links."""

    return HTMLResponse(
        render_staging_billing_activation(),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )

@staging_router.post("/stripe/webhook", response_model=WebhookResponse)
async def post_staging_stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> WebhookResponse:
    """Staging-only alias for the externally exposed isolated workspace host."""

    return await _process_stripe_webhook(request, stripe_signature)
