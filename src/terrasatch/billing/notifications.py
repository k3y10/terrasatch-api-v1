"""Durable TerraSatch billing-email rendering and provider delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
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


@dataclass(frozen=True, slots=True)
class BillingEmailMessage:
    subject: str
    text: str
    html: str


@dataclass(frozen=True, slots=True)
class BillingEmailDeliveryReceipt:
    provider: str
    message_id: str | None


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
        cancel_at_period_end=(
            subscription.cancel_at_period_end if subscription is not None else False
        ),
    )


async def get_account_email_context(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> BillingEmailContext | None:
    """Return a customer-safe email context for any enabled workspace member."""

    row = (
        await session.execute(
            select(User, Membership, Organization)
            .join(Membership, Membership.user_id == User.id)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(
                User.id == user_id,
                User.enabled.is_(True),
                Membership.enabled.is_(True),
                Organization.enabled.is_(True),
            )
            .order_by(Membership.created_at, Organization.name)
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    user, _membership, organization = row
    subscription = await session.scalar(
        select(Subscription).where(Subscription.organization_id == organization.id)
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
        cancel_at_period_end=(
            subscription.cancel_at_period_end if subscription is not None else False
        ),
    )


def notification_kind(
    *,
    stripe_event_type: str,
    activation_token: str | None,
    context: BillingEmailContext | None,
    previous_attributes: dict[str, object] | None = None,
) -> str | None:
    if activation_token:
        return "trial_started"
    if stripe_event_type == "customer.subscription.trial_will_end":
        return "trial_ending"
    if stripe_event_type == "invoice.payment_failed":
        return "payment_failed"
    if stripe_event_type == "invoice.paid":
        return "payment_confirmed"
    if stripe_event_type == "customer.subscription.deleted":
        return "subscription_ended"
    if (
        stripe_event_type == "customer.subscription.updated"
        and context is not None
        and context.cancel_at_period_end
    ):
        return "cancellation_scheduled"
    if (
        stripe_event_type == "customer.subscription.updated"
        and previous_attributes
        and any(key in previous_attributes for key in ("items", "plan", "quantity"))
    ):
        return "subscription_updated"
    return None


def _format_money(cents: int | None, interval: str | None) -> str | None:
    if cents is None or cents < 0:
        return None
    amount = f"${cents / 100:,.0f}"
    if interval == "monthly":
        return f"{amount}/month"
    if interval == "annual":
        return f"{amount}/year"
    return amount


def _format_date(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)
    normalized = normalized.astimezone(UTC)
    return f"{normalized.strftime('%B')} {normalized.day}, {normalized.year}"


def _button(href: str, label: str) -> str:
    return (
        '<p style="margin:28px 0">'
        f'<a href="{escape(href, quote=True)}" '
        'style="display:inline-block;background:#d97706;color:#fff;'
        'text-decoration:none;font-weight:700;padding:12px 18px;border-radius:8px">'
        f"{escape(label)}</a></p>"
    )


def _shell(title: str, body: str) -> str:
    return (
        '<!doctype html><html><body '
        'style="margin:0;background:#0b0f0d;color:#f4f4f0;font-family:Arial,sans-serif">'
        '<div style="max-width:620px;margin:0 auto;padding:36px 24px">'
        '<div style="font-size:12px;letter-spacing:.18em;color:#f59e0b;font-weight:700">'
        "TERRASATCH</div>"
        f'<h1 style="font-size:28px;line-height:1.15;margin:12px 0 20px">{escape(title)}</h1>'
        f'<div style="color:#d6d6cf;font-size:15px;line-height:1.65">{body}</div>'
        '<div style="margin-top:34px;padding-top:18px;border-top:1px solid #30342f;'
        'color:#8f968f;font-size:12px">LISTEN. WATCH. LEARN. ADAPT.</div>'
        "</div></body></html>"
    )


def build_billing_email(
    *,
    kind: str,
    context: BillingEmailContext,
    activation_url: str | None,
) -> BillingEmailMessage:
    name = escape(context.display_name or "there")
    organization = escape(context.organization_name)
    plan = escape(context.plan_name or "TerraSatch")
    price = _format_money(context.recurring_amount_cents, context.billing_interval)
    trial_end = _format_date(context.trial_ends_at)
    period_end = _format_date(context.current_period_end)
    grace_end = _format_date(context.grace_ends_at)

    if kind == "trial_started":
        subject = "Your TerraSatch trial is active"
        details = [
            f"<strong>Organization:</strong> {organization}",
            f"<strong>Plan:</strong> {plan}",
        ]
        if trial_end:
            details.append(f"<strong>Trial ends:</strong> {escape(trial_end)}")
        if price and trial_end:
            details.append(
                f"<strong>First scheduled charge:</strong> {escape(price)} "
                f"after {escape(trial_end)}"
            )
        activation = (
            _button(activation_url, "Activate TerraSatch account")
            if activation_url
            else ""
        )
        text_lines = [
            f"Hi {context.display_name or 'there'},",
            "",
            f"Your TerraSatch trial is active for {context.organization_name}.",
            f"Plan: {context.plan_name or 'TerraSatch'}",
        ]
        if trial_end:
            text_lines.append(f"Trial ends: {trial_end}")
        if price:
            text_lines.append(f"Recurring price: {price}")
        if activation_url:
            text_lines.extend(["", f"Activate your account: {activation_url}"])
        text_lines.extend(["", "LISTEN. WATCH. LEARN. ADAPT."])
        return BillingEmailMessage(
            subject=subject,
            text="\n".join(text_lines),
            html=_shell(
                subject,
                (
                    f"<p>Hi {name},</p>"
                    "<p>Your 30-day TerraSatch trial is active.</p>"
                    f"<p>{'<br>'.join(details)}</p>"
                    f"{activation}"
                    "<p>Stripe securely manages your payment method. "
                    "TerraSatch does not store card data.</p>"
                ),
            ),
        )

    if kind == "trial_ending":
        subject = "Your TerraSatch trial ends soon"
        ending_text = f" ends on {trial_end}" if trial_end else " ends soon"
        renewal_text = (
            f" Your subscription will continue at {price}."
            if price
            else ""
        )
        ending_html = (
            f" ends on <strong>{escape(trial_end)}</strong>"
            if trial_end
            else " ends soon"
        )
        renewal_html = ""
        if price:
            renewal_html = (
                "<p>Your subscription will continue at "
                f"<strong>{escape(price)}</strong> unless you cancel before "
                "the trial ends.</p>"
            )
        return BillingEmailMessage(
            subject=subject,
            text=(
                f"Hi {context.display_name or 'there'},\n\n"
                f"Your {context.plan_name or 'TerraSatch'} trial"
                f"{ending_text}.{renewal_text}\n\n"
                "You can manage billing from your TerraSatch organization portal."
            ),
            html=_shell(
                subject,
                (
                    f"<p>Hi {name},</p>"
                    f"<p>Your <strong>{plan}</strong> trial{ending_html}.</p>"
                    f"{renewal_html}"
                    "<p>You can manage billing from your TerraSatch "
                    "organization portal.</p>"
                ),
            ),
        )

    if kind == "payment_failed":
        subject = "Action needed: TerraSatch payment failed"
        grace_text = (
            f" Your organization remains in a temporary grace period through {grace_end}."
            if grace_end
            else ""
        )
        grace_html = ""
        if grace_end:
            grace_html = (
                "<p>Your organization remains in a temporary grace period through "
                f"<strong>{escape(grace_end)}</strong>.</p>"
            )
        return BillingEmailMessage(
            subject=subject,
            text=(
                f"Hi {context.display_name or 'there'},\n\n"
                "We could not process the latest TerraSatch payment for "
                f"{context.organization_name}.{grace_text}\n\n"
                "Please update the payment method from your TerraSatch organization portal."
            ),
            html=_shell(
                subject,
                (
                    f"<p>Hi {name},</p>"
                    "<p>We could not process the latest payment for "
                    f"<strong>{organization}</strong>.</p>"
                    f"{grace_html}"
                    "<p>Please update the payment method from your TerraSatch "
                    "organization portal.</p>"
                ),
            ),
        )

    if kind == "cancellation_scheduled":
        subject = "TerraSatch cancellation scheduled"
        ending_text = (
            f" at the end of the current period on {period_end}"
            if period_end
            else " at the end of the current billing period"
        )
        ending_html = (
            f" on <strong>{escape(period_end)}</strong>"
            if period_end
            else " at the end of the current billing period"
        )
        return BillingEmailMessage(
            subject=subject,
            text=(
                f"Hi {context.display_name or 'there'},\n\n"
                f"Your TerraSatch subscription for {context.organization_name} "
                f"is scheduled to cancel{ending_text}. "
                "Your data will not be deleted automatically."
            ),
            html=_shell(
                subject,
                (
                    f"<p>Hi {name},</p>"
                    f"<p>Your TerraSatch subscription for <strong>{organization}</strong> "
                    f"is scheduled to cancel{ending_html}.</p>"
                    "<p>Service remains available through the paid period. "
                    "TerraSatch does not automatically delete operational history "
                    "when billing ends.</p>"
                ),
            ),
        )

    if kind == "subscription_ended":
        subject = "Your TerraSatch subscription has ended"
        return BillingEmailMessage(
            subject=subject,
            text=(
                f"Hi {context.display_name or 'there'},\n\n"
                f"The TerraSatch subscription for {context.organization_name} has ended. "
                "Existing operational history is not automatically deleted. "
                "Contact TerraSatch if you need to reactivate the organization."
            ),
            html=_shell(
                subject,
                (
                    f"<p>Hi {name},</p>"
                    f"<p>The TerraSatch subscription for <strong>{organization}</strong> "
                    "has ended.</p>"
                    "<p>Existing operational history is not automatically deleted. "
                    "Contact TerraSatch if you need to reactivate the organization.</p>"
                ),
            ),
        )

    if kind == "activation_resend":
        subject = "Finish setting up your TerraSatch account"
        action = (
            _button(activation_url, "Finish TerraSatch setup")
            if activation_url
            else ""
        )
        return BillingEmailMessage(
            subject=subject,
            text=(
                f"Hi {context.display_name or 'there'},\n\n"
                "Your TerraSatch workspace is ready. "
                f"{'Finish setup: ' + activation_url if activation_url else 'Open TerraSatch to finish setup.'}\n\n"
                "If you did not request this message, you can ignore it."
            ),
            html=_shell(
                subject,
                (
                    f"<p>Hi {name},</p>"
                    f"<p>Your TerraSatch workspace for <strong>{organization}</strong> is ready.</p>"
                    f"{action}"
                    "<p>If you did not request this message, you can ignore it.</p>"
                ),
            ),
        )

    if kind == "password_reset":
        subject = "Reset your TerraSatch password"
        action = _button(activation_url, "Reset password") if activation_url else ""
        return BillingEmailMessage(
            subject=subject,
            text=(
                f"Hi {context.display_name or 'there'},\n\n"
                "A password reset was requested for your TerraSatch account. "
                f"{'Reset password: ' + activation_url if activation_url else ''}\n\n"
                "This link is single-use and expires shortly. "
                "If you did not request it, no action is needed."
            ),
            html=_shell(
                subject,
                (
                    f"<p>Hi {name},</p>"
                    "<p>A password reset was requested for your TerraSatch account.</p>"
                    f"{action}"
                    "<p>This link is single-use and expires shortly. "
                    "If you did not request it, no action is needed.</p>"
                ),
            ),
        )

    if kind == "payment_confirmed":
        subject = "TerraSatch payment received"
        amount = f" for {escape(price)}" if price else ""
        return BillingEmailMessage(
            subject=subject,
            text=(
                f"Hi {context.display_name or 'there'},\n\n"
                f"Stripe confirmed your TerraSatch payment{(' for ' + price) if price else ''}. "
                f"Your {context.plan_name or 'TerraSatch'} subscription remains active."
            ),
            html=_shell(
                subject,
                (
                    f"<p>Hi {name},</p>"
                    f"<p>Stripe confirmed your TerraSatch payment{amount}.</p>"
                    f"<p>Your <strong>{plan}</strong> subscription remains active.</p>"
                ),
            ),
        )

    if kind == "subscription_updated":
        subject = "Your TerraSatch subscription was updated"
        return BillingEmailMessage(
            subject=subject,
            text=(
                f"Hi {context.display_name or 'there'},\n\n"
                f"Your TerraSatch subscription is now {context.plan_name or 'TerraSatch'}"
                f"{(' at ' + price) if price else ''}. "
                "You can review billing from your TerraSatch workspace."
            ),
            html=_shell(
                subject,
                (
                    f"<p>Hi {name},</p>"
                    f"<p>Your TerraSatch subscription is now <strong>{plan}</strong>"
                    f"{(' at ' + escape(price)) if price else ''}.</p>"
                    "<p>You can review billing from your TerraSatch workspace.</p>"
                ),
            ),
        )

    raise ValueError("Unsupported billing email kind")

def _activation_url(settings: Settings, token: str | None) -> str | None:
    if not token:
        return None
    base_url = str(settings.billing_activation_url).split("#", 1)[0]
    return f"{base_url}#token={quote(token, safe='')}"


async def _deliver_direct_resend(
    *,
    settings: Settings,
    event_id: str,
    kind: str,
    context: BillingEmailContext,
    activation_url: str | None,
) -> BillingEmailDeliveryReceipt:
    if settings.resend_api_key is None or settings.billing_from is None:
        raise ProviderUnavailable("Direct Resend billing email is not configured")

    message = build_billing_email(
        kind=kind,
        context=context,
        activation_url=activation_url,
    )
    payload: dict[str, object] = {
        "from": settings.billing_from,
        "to": [context.to],
        "subject": message.subject,
        "text": message.text,
        "html": message.html,
    }
    if settings.billing_reply_to:
        payload["reply_to"] = settings.billing_reply_to

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"terrasatch-billing/{kind}/{event_id}"[:256],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers=headers,
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderUnavailable("Resend billing email delivery failed") from error

    message_id = str(data.get("id") or "").strip() if isinstance(data, dict) else ""
    return BillingEmailDeliveryReceipt(
        provider="resend",
        message_id=message_id[:255] or None,
    )


async def _deliver_via_webhook(
    *,
    settings: Settings,
    event_id: str,
    kind: str,
    context: BillingEmailContext,
    activation_url: str | None,
) -> BillingEmailDeliveryReceipt:
    if settings.billing_email_webhook_url is None or settings.billing_email_webhook_secret is None:
        raise ProviderUnavailable("Billing email webhook is not configured")

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
        data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderUnavailable("TerraSatch billing email webhook delivery failed") from error

    message_id = str(data.get("messageId") or "").strip() if isinstance(data, dict) else ""
    provider = "vercel_resend" if message_id else "vercel_webhook"
    return BillingEmailDeliveryReceipt(
        provider=provider,
        message_id=message_id[:255] or None,
    )


async def deliver_billing_email(
    *,
    settings: Settings,
    event_id: str,
    kind: str,
    context: BillingEmailContext,
    activation_token: str | None = None,
) -> BillingEmailDeliveryReceipt | None:
    """Deliver one idempotent lifecycle email through the configured provider.

    Direct Resend is preferred because the durable Oracle worker already owns retries.
    The protected Vercel endpoint is retained as a fallback for deployments where the
    API/worker does not hold Resend credentials.
    """

    activation_url = _activation_url(settings, activation_token)
    if settings.billing_resend_is_configured:
        return await _deliver_direct_resend(
            settings=settings,
            event_id=event_id,
            kind=kind,
            context=context,
            activation_url=activation_url,
        )
    if settings.billing_email_webhook_is_configured:
        return await _deliver_via_webhook(
            settings=settings,
            event_id=event_id,
            kind=kind,
            context=context,
            activation_url=activation_url,
        )
    return None
