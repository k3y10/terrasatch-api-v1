"""TerraSatch billing lifecycle, provisioning, and entitlement services."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.security import hash_admin_password
from terrasatch.billing.models import (
    BillingActivation,
    BillingCustomer,
    BillingSignup,
    StripeEvent,
    Subscription,
)
from terrasatch.billing.plans import (
    BillingInterval,
    PlanCode,
    PlanDefinition,
    get_plan,
    public_plan_catalog,
)
from terrasatch.billing.schemas import CheckoutRequest, SubscriptionResponse
from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ResourceConflict, ResourceNotFound
from terrasatch.identity.models import Account, Membership, MembershipRole, Organization, Site, User
from terrasatch.organizations.service import slugify

_ACTIVE_ACCESS_STATUSES = frozenset({"trialing", "active"})
_RESTRICTED_STATUSES = frozenset(
    {"canceled", "unpaid", "incomplete", "incomplete_expired", "paused"}
)


@dataclass(frozen=True, slots=True)
class ProvisioningResult:
    organization_id: UUID
    user_id: UUID
    activation_token: str | None
    newly_provisioned: bool
    state_applied: bool = True


@dataclass(frozen=True, slots=True)
class WebhookProcessingResult:
    duplicate: bool
    event_type: str
    organization_id: UUID | None = None
    activation_token: str | None = None
    activation_email: str | None = None
    state_applied: bool = True


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.utcoffset() is None else value.astimezone(UTC)


def _timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def recover_activation_token(settings: Settings, activation_id: UUID) -> str:
    secret = settings.billing_activation_signing_secret
    if secret is None:
        raise InvalidConfiguration("Activation signing secret is not configured")
    return hmac.new(
        secret.get_secret_value().encode(),
        f"terrasatch-activation-v1:{activation_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _event_payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _object_id(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        identifier = value.get("id")
        return str(identifier) if identifier else None
    return None


def _subscription_period(snapshot: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    """Read subscription periods across pre-Dahlia and current item-level Stripe shapes."""

    start = _timestamp(snapshot.get("current_period_start"))
    end = _timestamp(snapshot.get("current_period_end"))
    if start is not None or end is not None:
        return start, end

    items = snapshot.get("items")
    data = items.get("data", []) if isinstance(items, dict) else []
    if data and isinstance(data[0], dict):
        return _timestamp(data[0].get("current_period_start")), _timestamp(
            data[0].get("current_period_end")
        )
    return None, None


def _subscription_price_id(snapshot: dict[str, Any]) -> str | None:
    items = snapshot.get("items")
    data = items.get("data", []) if isinstance(items, dict) else []
    if not data or not isinstance(data[0], dict):
        return None
    price = data[0].get("price")
    return _object_id(price)


def _subscription_metadata(snapshot: dict[str, Any]) -> dict[str, str]:
    raw = snapshot.get("metadata")
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if value is not None}


def _invoice_subscription_id(invoice: dict[str, Any]) -> str | None:
    """Resolve subscription linkage from current Invoice.parent with legacy fallback."""

    parent = invoice.get("parent")
    if isinstance(parent, dict):
        details = parent.get("subscription_details")
        if isinstance(details, dict):
            identifier = _object_id(details.get("subscription"))
            if identifier:
                return identifier
    return _object_id(invoice.get("subscription"))


def _service_access(subscription: Subscription, *, now: datetime) -> str:
    status = subscription.status
    if status in _ACTIVE_ACCESS_STATUSES:
        return "full"
    if status == "past_due":
        grace_end = _as_utc(subscription.grace_ends_at)
        if grace_end is not None and grace_end > now:
            return "grace"
        return "restricted"
    if status in _RESTRICTED_STATUSES:
        return "restricted"
    return "restricted"


def public_plans() -> list[dict[str, object]]:
    return public_plan_catalog()


async def create_signup(
    session: AsyncSession,
    *,
    payload: CheckoutRequest,
    settings: Settings,
) -> BillingSignup:
    """Create or resume one bounded pre-Checkout record and block repeated trials."""

    plan = get_plan(payload.plan_code)
    if not plan.self_service:
        raise InvalidConfiguration("The selected plan requires a TerraSatch organization agreement")

    existing_user = await session.scalar(select(User).where(User.email == payload.email))
    if existing_user is not None:
        raise ResourceConflict(
            "An account already exists for this email. "
            "Sign in or contact TerraSatch to manage billing."
        )

    now = datetime.now(UTC)
    await session.execute(
        update(BillingSignup)
        .where(
            BillingSignup.email == payload.email,
            BillingSignup.status.in_(["pending", "checkout_created"]),
            BillingSignup.expires_at <= now,
        )
        .values(status="expired")
    )

    completed = await session.scalar(
        select(BillingSignup)
        .where(
            BillingSignup.email == payload.email,
            BillingSignup.status == "completed",
        )
        .order_by(BillingSignup.created_at.desc())
        .limit(1)
    )
    if completed is not None:
        raise ResourceConflict(
            "A TerraSatch trial already exists for this email.",
            details={"signup_id": str(completed.id), "status": completed.status},
        )

    existing_signup = await session.scalar(
        select(BillingSignup)
        .where(
            BillingSignup.email == payload.email,
            BillingSignup.status.in_(["pending", "checkout_created"]),
            BillingSignup.expires_at > now,
        )
        .order_by(BillingSignup.created_at.desc())
        .limit(1)
    )
    if existing_signup is not None:
        same_attempt = (
            existing_signup.organization_name == payload.organization_name
            and existing_signup.plan_code == payload.plan_code.value
            and existing_signup.billing_interval == payload.billing_interval.value
        )
        if not same_attempt:
            raise ResourceConflict(
                "An active TerraSatch Checkout already exists for this email. "
                "Finish or let it expire before changing the subscription selection.",
                details={
                    "signup_id": str(existing_signup.id),
                    "status": existing_signup.status,
                    "expires_at": _as_utc(existing_signup.expires_at).isoformat()
                    if _as_utc(existing_signup.expires_at)
                    else None,
                },
            )
        return existing_signup

    expires_at = now + timedelta(minutes=settings.billing_checkout_ttl_minutes)
    signup = BillingSignup(
        email=payload.email,
        display_name=payload.display_name,
        organization_name=payload.organization_name,
        plan_code=payload.plan_code.value,
        billing_interval=payload.billing_interval.value,
        status="pending",
        expires_at=expires_at,
    )
    session.add(signup)
    await session.flush()
    return signup


async def mark_checkout_created(
    session: AsyncSession,
    *,
    signup_id: UUID,
    checkout_session_id: str,
    checkout_expires_at: datetime,
) -> BillingSignup:
    signup = await session.get(BillingSignup, signup_id)
    if signup is None:
        raise ResourceNotFound("Billing signup was not found")
    if signup.status == "completed":
        return signup
    signup.stripe_checkout_session_id = checkout_session_id
    signup.status = "checkout_created"
    signup.expires_at = checkout_expires_at
    await session.flush()
    return signup


async def _find_signup(
    session: AsyncSession,
    *,
    signup_id: str | None,
    checkout_session_id: str | None = None,
    stripe_customer_id: str | None = None,
) -> BillingSignup:
    signup: BillingSignup | None = None
    if signup_id:
        try:
            signup = await session.get(BillingSignup, UUID(signup_id))
        except ValueError:
            signup = None
    if signup is None and checkout_session_id:
        signup = await session.scalar(
            select(BillingSignup).where(
                BillingSignup.stripe_checkout_session_id == checkout_session_id
            )
        )
    if signup is None and stripe_customer_id:
        signup = await session.scalar(
            select(BillingSignup)
            .where(BillingSignup.stripe_customer_id == stripe_customer_id)
            .order_by(BillingSignup.created_at.desc())
            .limit(1)
        )
    if signup is None:
        raise ResourceNotFound("Stripe event does not match a TerraSatch billing signup")
    return signup


async def _ensure_activation(
    session: AsyncSession,
    *,
    user: User,
    organization_id: UUID,
    settings: Settings,
) -> str | None:
    if user.password_hash:
        return None

    now = datetime.now(UTC)
    existing = await session.scalar(
        select(BillingActivation)
        .where(
            BillingActivation.user_id == user.id,
            BillingActivation.organization_id == organization_id,
            BillingActivation.consumed_at.is_(None),
            BillingActivation.expires_at > now,
        )
        .order_by(BillingActivation.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return None

    activation_id = uuid4()
    token = recover_activation_token(settings, activation_id)
    activation = BillingActivation(
        id=activation_id,
        user_id=user.id,
        organization_id=organization_id,
        token_hash=_token_hash(token),
        expires_at=now + timedelta(hours=settings.billing_activation_ttl_hours),
    )
    session.add(activation)
    await session.flush()
    return token


async def _provision_signup(
    session: AsyncSession,
    *,
    signup: BillingSignup,
    stripe_customer_id: str,
    settings: Settings,
) -> ProvisioningResult:
    billing_customer = await session.scalar(
        select(BillingCustomer).where(BillingCustomer.stripe_customer_id == stripe_customer_id)
    )
    if billing_customer is not None:
        user = await session.scalar(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == billing_customer.organization_id,
                Membership.role == MembershipRole.OWNER,
            )
            .limit(1)
        )
        if user is None:
            raise ResourceConflict("Billing customer exists without a TerraSatch owner")
        token = await _ensure_activation(
            session,
            user=user,
            organization_id=billing_customer.organization_id,
            settings=settings,
        )
        signup.status = "completed"
        signup.stripe_customer_id = stripe_customer_id
        signup.completed_at = signup.completed_at or datetime.now(UTC)
        return ProvisioningResult(
            organization_id=billing_customer.organization_id,
            user_id=user.id,
            activation_token=token,
            newly_provisioned=False,
        )

    existing_user = await session.scalar(select(User).where(User.email == signup.email))
    if existing_user is not None:
        raise ResourceConflict("This billing signup email is already bound to a TerraSatch user.")

    account = Account(name=signup.organization_name, enabled=True)
    session.add(account)
    await session.flush()

    organization = Organization(
        account_id=account.id,
        name=signup.organization_name,
        slug=slugify(signup.organization_name),
        enabled=True,
    )
    session.add(organization)
    await session.flush()

    # An operational container, not an invented geographic location. Create it in
    # the same transaction as the account so the first field note can be saved.
    session.add(
        Site(
            organization_id=organization.id,
            name=signup.organization_name,
            slug="primary",
            enabled=True,
        )
    )

    user = User(
        email=signup.email,
        display_name=signup.display_name,
        password_hash=None,
        enabled=True,
    )
    session.add(user)
    await session.flush()

    session.add(
        Membership(
            organization_id=organization.id,
            user_id=user.id,
            role=MembershipRole.OWNER,
            enabled=True,
        )
    )
    billing_customer = BillingCustomer(
        account_id=account.id,
        organization_id=organization.id,
        stripe_customer_id=stripe_customer_id,
    )
    session.add(billing_customer)
    await session.flush()

    signup.status = "completed"
    signup.stripe_customer_id = stripe_customer_id
    signup.completed_at = datetime.now(UTC)
    activation_token = await _ensure_activation(
        session,
        user=user,
        organization_id=organization.id,
        settings=settings,
    )
    return ProvisioningResult(
        organization_id=organization.id,
        user_id=user.id,
        activation_token=activation_token,
        newly_provisioned=True,
    )


def _validated_subscription_identity(
    snapshot: dict[str, Any],
) -> tuple[str, str, PlanCode, BillingInterval]:
    subscription_id = _object_id(snapshot.get("id"))
    customer_id = _object_id(snapshot.get("customer"))
    metadata = _subscription_metadata(snapshot)
    if not subscription_id or not customer_id:
        raise InvalidConfiguration("Stripe subscription event is missing required identifiers")
    try:
        plan_code = PlanCode(metadata["plan_code"])
        interval = BillingInterval(metadata["billing_interval"])
    except (KeyError, ValueError) as error:
        raise InvalidConfiguration(
            "Stripe subscription metadata is not a TerraSatch billing record"
        ) from error
    from terrasatch.billing.stripe_gateway import validate_price

    items = snapshot.get("items", {}).get("data", [])
    if len(items) != 1 or items[0].get("quantity") != 1:
        raise InvalidConfiguration("Subscription must contain exactly one plan at quantity one")
    validate_price(items[0].get("price"), get_plan(plan_code), interval)
    return subscription_id, customer_id, plan_code, interval


async def sync_subscription_snapshot(
    session: AsyncSession,
    *,
    snapshot: dict[str, Any],
    settings: Settings,
    event_created: int | None = None,
) -> ProvisioningResult:
    subscription_id, customer_id, plan_code, interval = _validated_subscription_identity(snapshot)
    metadata = _subscription_metadata(snapshot)
    signup = await _find_signup(
        session,
        signup_id=metadata.get("signup_id"),
        stripe_customer_id=customer_id,
    )
    if signup.plan_code != plan_code.value or signup.billing_interval != interval.value:
        raise InvalidConfiguration("Subscription does not match the original signup plan")
    provisioned = await _provision_signup(
        session,
        signup=signup,
        stripe_customer_id=customer_id,
        settings=settings,
    )
    billing_customer = await session.scalar(
        select(BillingCustomer).where(BillingCustomer.stripe_customer_id == customer_id)
    )
    if billing_customer is None:
        raise ResourceNotFound("TerraSatch billing customer was not provisioned")

    subscription = await session.scalar(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    if (
        subscription is not None
        and event_created is not None
        and subscription.last_subscription_event_created is not None
        and event_created < subscription.last_subscription_event_created
    ):
        return ProvisioningResult(
            organization_id=provisioned.organization_id,
            user_id=provisioned.user_id,
            activation_token=provisioned.activation_token,
            newly_provisioned=provisioned.newly_provisioned,
            state_applied=False,
        )
    if subscription is None:
        subscription = Subscription(
            organization_id=billing_customer.organization_id,
            billing_customer_id=billing_customer.id,
            stripe_subscription_id=subscription_id,
            plan_code=plan_code.value,
            billing_interval=interval.value,
            status=str(snapshot.get("status") or "incomplete"),
        )
        session.add(subscription)

    period_start, period_end = _subscription_period(snapshot)
    subscription.organization_id = billing_customer.organization_id
    subscription.billing_customer_id = billing_customer.id
    subscription.stripe_price_id = _subscription_price_id(snapshot)
    subscription.plan_code = plan_code.value
    subscription.billing_interval = interval.value
    subscription.status = str(snapshot.get("status") or subscription.status)
    subscription.trial_started_at = _timestamp(snapshot.get("trial_start"))
    subscription.trial_ends_at = _timestamp(snapshot.get("trial_end"))
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end
    subscription.cancel_at_period_end = bool(snapshot.get("cancel_at_period_end", False))
    if subscription.status in _ACTIVE_ACCESS_STATUSES:
        subscription.grace_ends_at = None
        subscription.last_payment_failed_at = None
    if event_created is not None:
        subscription.last_subscription_event_created = event_created
    await session.flush()
    return provisioned


async def _sync_checkout_completed(
    session: AsyncSession,
    *,
    checkout: dict[str, Any],
    subscription_snapshot: dict[str, Any] | None,
    settings: Settings,
    event_created: int | None = None,
) -> ProvisioningResult:
    checkout_id = _object_id(checkout.get("id"))
    customer_id = _object_id(checkout.get("customer"))
    metadata = checkout.get("metadata") if isinstance(checkout.get("metadata"), dict) else {}
    signup_id = str(metadata.get("signup_id") or checkout.get("client_reference_id") or "")
    signup = await _find_signup(
        session,
        signup_id=signup_id or None,
        checkout_session_id=checkout_id,
    )

    customer_details = checkout.get("customer_details")
    checkout_email = None
    if isinstance(customer_details, dict):
        checkout_email = customer_details.get("email")
    if not checkout_email:
        checkout_email = checkout.get("customer_email")
    if not isinstance(checkout_email, str) or checkout_email.strip().casefold() != signup.email:
        raise InvalidConfiguration("Completed Checkout email does not match the TerraSatch signup")

    if not customer_id and subscription_snapshot is not None:
        customer_id = _object_id(subscription_snapshot.get("customer"))
    if not customer_id:
        raise InvalidConfiguration("Completed Stripe Checkout is missing a customer")
    signup.stripe_checkout_session_id = checkout_id or signup.stripe_checkout_session_id
    provisioned = await _provision_signup(
        session,
        signup=signup,
        stripe_customer_id=customer_id,
        settings=settings,
    )
    if subscription_snapshot is not None:
        await sync_subscription_snapshot(
            session,
            snapshot=subscription_snapshot,
            settings=settings,
            event_created=event_created,
        )
    return provisioned


async def _mark_invoice_failed(
    session: AsyncSession,
    *,
    invoice: dict[str, Any],
    settings: Settings,
    event_created: int | None = None,
) -> tuple[UUID | None, bool]:
    subscription_id = _invoice_subscription_id(invoice)
    if not subscription_id:
        return None, True
    subscription = await session.scalar(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    if subscription is None:
        return None, True
    if (
        event_created is not None
        and subscription.last_invoice_event_created is not None
        and event_created < subscription.last_invoice_event_created
    ):
        return subscription.organization_id, False
    now = datetime.now(UTC)
    subscription.status = "past_due"
    subscription.last_invoice_id = _object_id(invoice.get("id"))
    subscription.last_payment_failed_at = now
    subscription.grace_ends_at = now + timedelta(days=settings.billing_grace_days)
    if event_created is not None:
        subscription.last_invoice_event_created = event_created
    await session.flush()
    return subscription.organization_id, True


async def _mark_invoice_paid(
    session: AsyncSession,
    *,
    invoice: dict[str, Any],
    event_created: int | None = None,
) -> tuple[UUID | None, bool]:
    subscription_id = _invoice_subscription_id(invoice)
    if not subscription_id:
        return None, True
    subscription = await session.scalar(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    if subscription is None:
        return None, True
    if (
        event_created is not None
        and subscription.last_invoice_event_created is not None
        and event_created < subscription.last_invoice_event_created
    ):
        return subscription.organization_id, False
    subscription.last_invoice_id = _object_id(invoice.get("id"))
    if subscription.status == "past_due":
        subscription.status = "active"
    subscription.grace_ends_at = None
    subscription.last_payment_failed_at = None
    if event_created is not None:
        subscription.last_invoice_event_created = event_created
    await session.flush()
    return subscription.organization_id, True


async def process_verified_event(
    session: AsyncSession,
    *,
    event: dict[str, Any],
    raw_payload: bytes,
    settings: Settings,
    subscription_snapshot: dict[str, Any] | None = None,
) -> WebhookProcessingResult:
    """Apply one verified Stripe event transactionally and exactly once."""

    event_id = _object_id(event.get("id"))
    event_type = str(event.get("type") or "")
    raw_event_created = event.get("created")
    event_created = (
        raw_event_created
        if isinstance(raw_event_created, int)
        and not isinstance(raw_event_created, bool)
        and raw_event_created >= 0
        else None
    )
    if not event_id or not event_type:
        raise InvalidConfiguration("Stripe webhook event is missing an ID or type")
    # Serialize lifecycle events across workers before provisioning or checking the ledger.
    # This low-volume billing lock is transaction-scoped and automatically released.
    if session.bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(73429101)"))
    existing = await session.get(StripeEvent, event_id)
    if existing is not None:
        return WebhookProcessingResult(duplicate=True, event_type=event_type)

    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        raise InvalidConfiguration("Stripe webhook event is missing its data object")

    result = WebhookProcessingResult(duplicate=False, event_type=event_type)
    if event_type == "checkout.session.completed":
        provisioned = await _sync_checkout_completed(
            session,
            checkout=obj,
            subscription_snapshot=subscription_snapshot,
            settings=settings,
            event_created=event_created,
        )
        signup = await _find_signup(
            session,
            signup_id=str(
                (obj.get("metadata") or {}).get("signup_id")
                if isinstance(obj.get("metadata"), dict)
                else obj.get("client_reference_id") or ""
            )
            or None,
            checkout_session_id=_object_id(obj.get("id")),
        )
        result = WebhookProcessingResult(
            duplicate=False,
            event_type=event_type,
            organization_id=provisioned.organization_id,
            activation_token=provisioned.activation_token,
            activation_email=signup.email,
        )
    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.trial_will_end",
    }:
        provisioned = await sync_subscription_snapshot(
            session,
            snapshot=obj,
            settings=settings,
            event_created=event_created,
        )
        billing_customer = await session.scalar(
            select(BillingCustomer).where(
                BillingCustomer.organization_id == provisioned.organization_id
            )
        )
        signup = None
        if billing_customer is not None:
            signup = await session.scalar(
                select(BillingSignup)
                .where(BillingSignup.stripe_customer_id == billing_customer.stripe_customer_id)
                .order_by(BillingSignup.created_at.desc())
                .limit(1)
            )
        result = WebhookProcessingResult(
            duplicate=False,
            event_type=event_type,
            organization_id=provisioned.organization_id,
            activation_token=provisioned.activation_token,
            activation_email=signup.email if signup is not None else None,
            state_applied=provisioned.state_applied,
        )
    elif event_type == "invoice.payment_failed":
        organization_id, state_applied = await _mark_invoice_failed(
            session,
            invoice=obj,
            settings=settings,
            event_created=event_created,
        )
        result = WebhookProcessingResult(
            duplicate=False,
            event_type=event_type,
            organization_id=organization_id,
            state_applied=state_applied,
        )
    elif event_type == "invoice.paid":
        organization_id, state_applied = await _mark_invoice_paid(
            session,
            invoice=obj,
            event_created=event_created,
        )
        result = WebhookProcessingResult(
            duplicate=False,
            event_type=event_type,
            organization_id=organization_id,
            state_applied=state_applied,
        )

    session.add(
        StripeEvent(
            event_id=event_id,
            event_type=event_type,
            livemode=bool(event.get("livemode", False)),
            payload_sha256=_event_payload_hash(raw_payload),
            provider_created_at=event_created,
            processed_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return result


async def get_subscription_for_organization(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> SubscriptionResponse:
    subscription = await session.scalar(
        select(Subscription).where(Subscription.organization_id == organization_id)
    )
    if subscription is None:
        return SubscriptionResponse(
            organization_id=organization_id,
            managed=False,
            plan_code=None,
            billing_interval=None,
            status="legacy",
            service_access="legacy",
            trial_ends_at=None,
            current_period_end=None,
            cancel_at_period_end=False,
            grace_ends_at=None,
            entitlements=None,
        )

    try:
        plan_code = PlanCode(subscription.plan_code)
        interval = BillingInterval(subscription.billing_interval)
        plan: PlanDefinition = get_plan(plan_code)
        entitlements = asdict(plan.entitlements)
    except ValueError:
        plan_code = None
        interval = None
        entitlements = None

    return SubscriptionResponse(
        organization_id=organization_id,
        managed=True,
        plan_code=plan_code,
        billing_interval=interval,
        status=subscription.status,
        service_access=_service_access(subscription, now=datetime.now(UTC)),
        trial_ends_at=_as_utc(subscription.trial_ends_at),
        current_period_end=_as_utc(subscription.current_period_end),
        cancel_at_period_end=subscription.cancel_at_period_end,
        grace_ends_at=_as_utc(subscription.grace_ends_at),
        entitlements=entitlements,
    )


async def get_stripe_customer_id(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> str:
    billing_customer = await session.scalar(
        select(BillingCustomer).where(BillingCustomer.organization_id == organization_id)
    )
    if billing_customer is None:
        raise ResourceNotFound("This organization does not have self-service billing")
    return billing_customer.stripe_customer_id


async def recover_pending_activation_token_for_checkout(
    session: AsyncSession,
    *,
    checkout_session_id: str,
    settings: Settings,
) -> tuple[str, str] | None:
    """Recover a pending activation token and owner email for isolated staging onboarding."""

    signup = await session.scalar(
        select(BillingSignup).where(
            BillingSignup.stripe_checkout_session_id == checkout_session_id,
            BillingSignup.status == "completed",
        )
    )
    if signup is None or not signup.stripe_customer_id:
        return None

    billing_customer = await session.scalar(
        select(BillingCustomer).where(
            BillingCustomer.stripe_customer_id == signup.stripe_customer_id
        )
    )
    if billing_customer is None:
        return None

    now = datetime.now(UTC)
    activation = await session.scalar(
        select(BillingActivation)
        .where(
            BillingActivation.organization_id == billing_customer.organization_id,
            BillingActivation.consumed_at.is_(None),
            BillingActivation.expires_at > now,
        )
        .order_by(BillingActivation.created_at.desc())
        .limit(1)
    )
    if activation is None:
        return None

    token = recover_activation_token(settings, activation.id)
    if _token_hash(token) != activation.token_hash:
        raise InvalidConfiguration("Activation signing secret does not match staging state")
    return token, signup.email


async def recover_or_refresh_activation_for_email(
    session: AsyncSession,
    *,
    email: str,
    settings: Settings,
) -> tuple[str, UUID] | None:
    """Return a valid owner activation token without disclosing account existence."""

    normalized = email.strip().casefold()
    user = await session.scalar(
        select(User).where(User.email == normalized, User.enabled.is_(True))
    )
    if user is None or user.password_hash:
        return None

    membership = await session.scalar(
        select(Membership)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == user.id,
            Membership.role == MembershipRole.OWNER,
            Membership.enabled.is_(True),
            Organization.enabled.is_(True),
        )
        .order_by(Membership.created_at)
        .limit(1)
    )
    if membership is None:
        return None

    now = datetime.now(UTC)
    activation = await session.scalar(
        select(BillingActivation)
        .where(
            BillingActivation.user_id == user.id,
            BillingActivation.organization_id == membership.organization_id,
            BillingActivation.consumed_at.is_(None),
            BillingActivation.expires_at > now,
        )
        .order_by(BillingActivation.created_at.desc())
        .limit(1)
    )
    if activation is None:
        activation_id = uuid4()
        token = recover_activation_token(settings, activation_id)
        activation = BillingActivation(
            id=activation_id,
            user_id=user.id,
            organization_id=membership.organization_id,
            token_hash=_token_hash(token),
            expires_at=now + timedelta(hours=settings.billing_activation_ttl_hours),
        )
        session.add(activation)
        await session.flush()
        return token, membership.organization_id

    token = recover_activation_token(settings, activation.id)
    if _token_hash(token) != activation.token_hash:
        raise InvalidConfiguration("Activation signing secret does not match account state")
    return token, membership.organization_id


async def activate_owner(
    session: AsyncSession,
    *,
    token: str,
    password: str,
) -> UUID:
    now = datetime.now(UTC)
    activation = await session.scalar(
        select(BillingActivation)
        .where(
            BillingActivation.token_hash == _token_hash(token),
            BillingActivation.consumed_at.is_(None),
            BillingActivation.expires_at > now,
        )
        .with_for_update()
    )
    if activation is None:
        raise ResourceNotFound("Activation token is invalid, expired, or already used")
    user = await session.get(User, activation.user_id)
    if user is None or not user.enabled:
        raise ResourceNotFound("Activation user was not found")
    try:
        user.password_hash = hash_admin_password(password)
        user.credential_version += 1
    except ValueError as error:
        raise InvalidConfiguration(str(error)) from error
    activation.consumed_at = now
    await session.flush()
    return activation.organization_id


async def edge_service_payload(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> dict[str, object]:
    """Return only service state Edge needs; never expose Stripe/customer identifiers."""

    subscription = await get_subscription_for_organization(
        session,
        organization_id=organization_id,
    )
    return {
        "status": subscription.service_access,
        "plan": subscription.plan_code.value if subscription.plan_code else None,
        "billing_status": subscription.status,
        "trial_ends_at": subscription.trial_ends_at.isoformat()
        if subscription.trial_ends_at
        else None,
        "grace_ends_at": subscription.grace_ends_at.isoformat()
        if subscription.grace_ends_at
        else None,
        "entitlements": subscription.entitlements.model_dump()
        if subscription.entitlements is not None
        else None,
    }
