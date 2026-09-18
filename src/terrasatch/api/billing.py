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
    process_verified_event,
    public_plans,
    recover_pending_activation_token_for_checkout,
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
    """Create a 30-day subscription trial in Stripe Checkout without trusting price IDs."""

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

    if settings.staging_payment_links_are_configured and settings.stripe_secret_key is None:
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
                and result.organization_id is not None
                and settings.billing_email_is_configured
            ):
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


STAGING_BILLING_STYLES = """<style>
:root{color-scheme:dark;--bg:#080b0d;--panel:#101519;--panel2:#0c1114;--line:rgba(255,255,255,.11);--text:#edf1f0;--muted:#8f989e;--orange:#f47a20;--orange2:#f59e0b;--green:#6ee7a0;--red:#ff7b7b;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}html{min-height:100%;background:var(--bg)}body{margin:0;min-height:100vh;color:var(--text);font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 72% -10%,rgba(244,122,32,.15),transparent 34%),linear-gradient(rgba(244,122,32,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(244,122,32,.02) 1px,transparent 1px),var(--bg);background-size:auto,48px 48px,48px 48px,auto}
a{color:inherit}.shell{width:min(1080px,calc(100% - 32px));margin:0 auto;padding:28px 0 64px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:8px 0 28px}.brand{display:flex;align-items:center;gap:12px;text-decoration:none}.brand-mark{width:42px;height:42px;border:1px solid rgba(244,122,32,.5);border-radius:12px;display:grid;place-items:center;background:rgba(244,122,32,.08);box-shadow:0 0 28px rgba(244,122,32,.09);font:800 18px var(--mono);color:var(--orange)}.brand strong{display:block;font-size:15px;letter-spacing:.08em}.brand span{display:block;color:var(--orange);font:700 9px var(--mono);letter-spacing:.16em;margin-top:2px}.env{border:1px solid var(--line);border-radius:999px;padding:7px 10px;color:var(--muted);font:700 9px var(--mono);letter-spacing:.14em}.layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr);gap:18px}.card{border:1px solid var(--line);border-radius:18px;background:linear-gradient(145deg,rgba(16,21,25,.96),rgba(10,14,17,.95));box-shadow:0 28px 80px rgba(0,0,0,.28);overflow:hidden}.main{padding:36px}.side{padding:28px}.eyebrow{margin:0;color:var(--orange);font:800 10px var(--mono);letter-spacing:.18em;text-transform:uppercase}.hero h1{margin:10px 0 12px;font-size:clamp(34px,5vw,58px);line-height:.98;letter-spacing:-.035em}.hero p{margin:0;max-width:700px;color:var(--muted);font-size:16px}.steps{display:grid;grid-template-columns:repeat(4,1fr);margin:34px 0 30px;border:1px solid var(--line);border-radius:12px;overflow:hidden}.step{padding:13px 12px;background:rgba(8,11,13,.5);border-right:1px solid var(--line)}.step:last-child{border-right:0}.step b{display:block;color:var(--muted);font:800 9px var(--mono);letter-spacing:.12em;text-transform:uppercase}.step span{display:block;margin-top:4px;font-weight:700;font-size:12px}.step.done b,.step.active b{color:var(--orange)}.step.done span{color:#dfe7e3}.step.active{background:rgba(244,122,32,.065)}.status-box{display:flex;gap:14px;align-items:flex-start;border:1px solid rgba(244,122,32,.26);background:rgba(244,122,32,.045);border-radius:12px;padding:16px}.status-dot{width:11px;height:11px;border-radius:50%;background:var(--orange);margin-top:6px;box-shadow:0 0 15px rgba(244,122,32,.55);flex:0 0 auto}.status-dot.ok{background:var(--green);box-shadow:0 0 15px rgba(110,231,160,.45)}.status-dot.error{background:var(--red);box-shadow:0 0 15px rgba(255,123,123,.4)}.status-box strong{display:block;font-size:15px}.status-box p{margin:3px 0 0;color:var(--muted);font-size:13px}.setup{display:none;margin-top:22px;padding-top:22px;border-top:1px solid var(--line)}.setup.visible{display:block}.setup h2{margin:0;font-size:23px}.setup>p{margin:7px 0 18px;color:var(--muted);font-size:13px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}label{display:grid;gap:7px;color:#cbd2cf;font-size:12px;font-weight:700}input{width:100%;height:48px;border:1px solid var(--line);border-radius:9px;background:#090d0f;color:var(--text);padding:0 13px;font:14px inherit;outline:none}input:focus{border-color:rgba(244,122,32,.75);box-shadow:0 0 0 3px rgba(244,122,32,.08)}button,.button{display:inline-flex;align-items:center;justify-content:center;min-height:48px;border:1px solid rgba(244,122,32,.5);border-radius:9px;background:linear-gradient(180deg,#fa852d,#e96c12);color:#140c05;padding:0 18px;font-weight:900;text-decoration:none;cursor:pointer;box-shadow:0 12px 30px rgba(244,122,32,.12)}button:hover,.button:hover{filter:brightness(1.05)}button:disabled{opacity:.55;cursor:not-allowed}.ghost{background:transparent;color:var(--text);border-color:var(--line);box-shadow:none}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.error-text{min-height:22px;color:#ff9a9a;font-size:12px;margin-top:10px}.meta{display:grid;gap:1px;border:1px solid var(--line);border-radius:12px;overflow:hidden}.meta div{padding:16px;background:rgba(8,11,13,.54)}.meta small{display:block;color:var(--muted);font:800 9px var(--mono);letter-spacing:.12em;text-transform:uppercase}.meta strong{display:block;margin-top:5px;font-size:17px}.trust{margin-top:18px;border-top:1px solid var(--line);padding-top:18px;color:var(--muted);font-size:12px}.trust b{color:#dbe3df}.footer{margin-top:18px;color:#5f696e;font:9px var(--mono);letter-spacing:.12em;text-align:center;text-transform:uppercase}.simple{max-width:680px;margin:9vh auto 0}.simple .main{padding:38px}.simple h1{margin:9px 0 12px;font-size:42px;line-height:1}.simple p{color:var(--muted)}@media(max-width:780px){.layout{grid-template-columns:1fr}.main,.side{padding:24px}.steps{grid-template-columns:1fr 1fr}.step:nth-child(2){border-right:0}.step:nth-child(-n+2){border-bottom:1px solid var(--line)}.grid2{grid-template-columns:1fr}.topbar{padding-bottom:18px}.hero h1{font-size:38px}}
</style>"""


def _staging_billing_head(title: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        '<meta name="theme-color" content="#080b0d">'
        f"<title>{title}</title>{STAGING_BILLING_STYLES}</head>"
    )


def _staging_brand_header() -> str:
    return """<div class="topbar">
<a class="brand" href="https://terrasatch.com/">
  <span class="brand-mark">TS</span>
  <span><strong>TERRASATCH</strong><span>LISTEN · WATCH · LEARN · ADAPT</span></span>
</a>
<span class="env">STAGING · STRIPE SANDBOX</span>
</div>"""


@staging_router.get("/success", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_success() -> HTMLResponse:
    """Render branded staging onboarding and complete activation inline."""

    html = (
        _staging_billing_head("TerraSatch · Finish setup")
        + """<body><div class="shell">"""
        + _staging_brand_header()
        + """<div class="layout">
<section class="card main">
  <div class="hero">
    <p class="eyebrow">Secure setup</p>
    <h1>Your field workspace is almost ready.</h1>
    <p>Stripe has your payment method. TerraSatch is syncing the subscription, creating your organization, and connecting your workspace.</p>
  </div>

  <div class="steps">
    <div class="step done"><b>01</b><span>Plan selected</span></div>
    <div class="step done"><b>02</b><span>Secure checkout</span></div>
    <div class="step active" id="step-access"><b>03</b><span>Create access</span></div>
    <div class="step" id="step-workspace"><b>04</b><span>Workspace</span></div>
  </div>

  <div class="status-box" id="status-box">
    <span class="status-dot" id="status-dot"></span>
    <div><strong id="status-title">Connecting your subscription</strong><p id="status-copy">Waiting for Stripe and TerraSatch to finish provisioning.</p></div>
  </div>

  <form class="setup" id="setup">
    <h2>Create your TerraSatch password</h2>
    <p>One password finishes setup. You will be signed in automatically when activation completes.</p>
    <div class="grid2">
      <label>Password<input id="password" type="password" minlength="12" autocomplete="new-password" required></label>
      <label>Confirm password<input id="confirm-password" type="password" minlength="12" autocomplete="new-password" required></label>
    </div>
    <div class="error-text" id="form-error" role="alert"></div>
    <div class="actions">
      <button id="activate-button" type="submit">Create access &amp; open workspace</button>
    </div>
  </form>

  <div class="actions" id="existing-actions" style="display:none">
    <a class="button" href="/portal/login">Sign in to workspace</a>
  </div>
</section>

<aside class="card side">
  <p class="eyebrow">Your subscription</p>
  <div class="meta" style="margin-top:14px">
    <div><small>Today</small><strong>$0</strong></div>
    <div><small>Plan</small><strong id="plan">Connecting…</strong></div>
    <div><small>After trial</small><strong id="price">—</strong></div>
    <div><small>Trial ends</small><strong id="trial-end">—</strong></div>
  </div>
  <div class="trust">
    <b>Payment stays with Stripe.</b><br>
    TerraSatch receives subscription status and service access. Card details are not stored in the TerraSatch workspace.
  </div>
</aside>
</div>
<div class="footer">TerraSatch staging · real provider flow · live billing disabled</div>
</div>
<script>
const sessionId = new URLSearchParams(location.search).get("session_id");
const statusBox = document.getElementById("status-box");
const statusDot = document.getElementById("status-dot");
const statusTitle = document.getElementById("status-title");
const statusCopy = document.getElementById("status-copy");
const setup = document.getElementById("setup");
const formError = document.getElementById("form-error");
const activateButton = document.getElementById("activate-button");
const stepAccess = document.getElementById("step-access");
const stepWorkspace = document.getElementById("step-workspace");
const existingActions = document.getElementById("existing-actions");
let activationToken = "";
let ownerEmail = "";
let attempts = 0;

function money(cents) {
  return new Intl.NumberFormat("en-US", {style:"currency",currency:"USD",maximumFractionDigits:0}).format((cents || 0) / 100) + "/month";
}
function dateLabel(value) {
  if (!value) return "Pending";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Pending" : date.toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"});
}
function setStatus(kind, title, copy) {
  statusDot.className = "status-dot" + (kind ? " " + kind : "");
  statusTitle.textContent = title;
  statusCopy.textContent = copy;
}
async function loadActivation() {
  const response = await fetch("/api/v1/workspace/billing/checkout/activation?session_id=" + encodeURIComponent(sessionId), {credentials:"same-origin"});
  if (!response.ok) throw new Error("TerraSatch could not prepare account access.");
  const activation = await response.json();
  activationToken = activation.token || "";
  ownerEmail = activation.email || "";
  history.replaceState({}, document.title, location.pathname);
  if (!activationToken || !ownerEmail) {
    stepAccess.classList.add("done");
    stepAccess.classList.remove("active");
    stepWorkspace.classList.add("active");
    existingActions.style.display = "flex";
    setStatus("ok", "Workspace already activated", "Sign in with the TerraSatch account you already created.");
    return;
  }
  setup.classList.add("visible");
  setStatus("ok", "Workspace created", "Create one password to finish setup and open your connected workspace.");
}
async function check() {
  if (!sessionId) {
    setStatus("error", "Checkout session missing", "Return to TerraSatch pricing and start checkout again.");
    return;
  }
  attempts += 1;
  try {
    const response = await fetch("/api/v1/workspace/billing/checkout/status?session_id=" + encodeURIComponent(sessionId), {credentials:"same-origin"});
    if (!response.ok) throw new Error("Status unavailable");
    const data = await response.json();
    document.getElementById("plan").textContent = (data.plan_code || "TerraSatch").replace(/^./, c => c.toUpperCase());
    document.getElementById("price").textContent = money(data.recurring_amount_cents);
    document.getElementById("trial-end").textContent = dateLabel(data.trial_ends_at);

    if (data.state === "ready") {
      if (data.activation_required) {
        await loadActivation();
      } else {
        history.replaceState({}, document.title, location.pathname);
        stepAccess.classList.add("done");
        stepAccess.classList.remove("active");
        stepWorkspace.classList.add("active");
        existingActions.style.display = "flex";
        setStatus("ok", "Workspace connected", "Your subscription and workspace are ready. Sign in to continue.");
      }
      return;
    }
    if (data.state === "expired") {
      setStatus("error", "Checkout expired", "No TerraSatch subscription was activated from this Checkout session.");
      return;
    }
    setStatus("", "Connecting your subscription", "Stripe checkout is complete. TerraSatch is finishing workspace provisioning.");
  } catch {
    setStatus("", "Still connecting", "The secure webhook is still processing. TerraSatch will check again automatically.");
  }
  if (attempts < 30) setTimeout(check, 1500);
  else setStatus("error", "Setup is taking longer than expected", "Your payment was not duplicated. Refresh this page to check the canonical TerraSatch state.");
}

setup.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  const passwordInput = document.getElementById("password");
  const confirmInput = document.getElementById("confirm-password");
  const password = passwordInput.value;
  if (password.length < 12) { formError.textContent = "Use at least 12 characters."; return; }
  if (password !== confirmInput.value) { formError.textContent = "Passwords do not match."; return; }
  if (!activationToken || !ownerEmail) { formError.textContent = "Secure activation context is unavailable. Refresh this page."; return; }

  activateButton.disabled = true;
  activateButton.textContent = "Connecting workspace…";
  try {
    const activationResponse = await fetch("/api/v1/workspace/billing/activate", {
      method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({token:activationToken,password})
    });
    const activationData = await activationResponse.json().catch(() => ({}));
    if (!activationResponse.ok) throw new Error(activationData?.error?.message || activationData?.detail || "Account activation failed.");

    const loginResponse = await fetch("/api/v1/workspace/login", {
      method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({email:ownerEmail,password})
    });
    const loginData = await loginResponse.json().catch(() => ({}));
    if (!loginResponse.ok) throw new Error(loginData?.detail || "Account activated, but automatic sign-in failed.");

    activationToken = "";
    ownerEmail = "";
    passwordInput.value = "";
    confirmInput.value = "";
    stepAccess.classList.add("done");
    stepAccess.classList.remove("active");
    stepWorkspace.classList.add("active");
    setStatus("ok", "Workspace connected", "Your account is active. Opening TerraSatch now.");
    setTimeout(() => location.replace("/portal"), 650);
  } catch (error) {
    formError.textContent = error instanceof Error ? error.message : "TerraSatch could not finish setup.";
    activateButton.disabled = false;
    activateButton.textContent = "Create access & open workspace";
  }
});

check();
</script></body></html>"""
    )
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@staging_router.get("/cancel", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_cancel() -> HTMLResponse:
    """Render a branded staging Checkout cancellation landing page."""

    html = (
        _staging_billing_head("TerraSatch · Checkout canceled")
        + """<body><div class="shell simple">"""
        + _staging_brand_header()
        + """<section class="card main"><p class="eyebrow">Checkout</p>
<h1>No changes were made.</h1>
<p>Checkout was canceled before a subscription was activated. You can return to TerraSatch and choose a plan whenever you are ready.</p>
<div class="actions"><a class="button" href="https://terrasatch.com/#cost">Return to plans</a></div>
</section><div class="footer">TerraSatch staging · Stripe sandbox</div></div></body></html>"""
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@staging_router.get("/portal-return", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_portal_return() -> HTMLResponse:
    """Render a branded safe return target for Stripe Customer Portal acceptance."""

    html = (
        _staging_billing_head("TerraSatch · Billing updated")
        + """<body><div class="shell simple">"""
        + _staging_brand_header()
        + """<section class="card main"><p class="eyebrow">Billing</p>
<h1>Billing settings updated.</h1>
<p>Your Stripe billing session is complete. Return to TerraSatch to continue working with the organization.</p>
<div class="actions"><a class="button" href="/portal">Open workspace</a></div>
</section><div class="footer">TerraSatch staging · Stripe sandbox</div></div></body></html>"""
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@staging_router.get("/activate", response_class=HTMLResponse, include_in_schema=False)
async def get_staging_billing_activation() -> HTMLResponse:
    """Render the branded legacy activation page for emailed staging links."""

    html = (
        _staging_billing_head("TerraSatch · Activate account")
        + """<body><div class="shell simple">"""
        + _staging_brand_header()
        + """<section class="card main"><p class="eyebrow">Secure account access</p>
<h1>Create your TerraSatch password.</h1>
<p>This single-use activation link finishes account setup. New Checkout flows complete this step inline automatically.</p>
<form id="activation" class="setup visible">
<label>Password<input id="password" type="password" minlength="12" autocomplete="new-password" required></label>
<div class="error-text" id="result" role="alert"></div>
<div class="actions"><button type="submit">Activate account</button></div>
</form>
</section><div class="footer">TerraSatch · secure account activation</div></div>
<script>
const token = new URLSearchParams(location.hash.slice(1)).get("token");
history.replaceState({}, document.title, location.pathname);
const form = document.getElementById("activation");
const result = document.getElementById("result");
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!token) { result.textContent = "Activation token is missing."; return; }
  const password = document.getElementById("password").value;
  const response = await fetch("/api/v1/workspace/billing/activate", {
    method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({token,password})
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    result.textContent = data?.error?.message || data?.detail || "Activation failed.";
    return;
  }
  result.style.color = "var(--green)";
  result.textContent = "Account activated. Continue to sign in.";
  setTimeout(() => location.replace("/portal/login"), 700);
});
</script></body></html>"""
    )
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@staging_router.post("/stripe/webhook", response_model=WebhookResponse)
async def post_staging_stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> WebhookResponse:
    """Staging-only alias for the externally exposed isolated workspace host."""

    return await _process_stripe_webhook(request, stripe_signature)
