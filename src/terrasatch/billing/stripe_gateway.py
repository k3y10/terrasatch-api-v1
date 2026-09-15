"""Stripe Billing gateway isolated from TerraSatch domain state."""

from __future__ import annotations

import asyncio
import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from stripe import StripeClient

from terrasatch.billing.plans import BillingInterval, PlanDefinition
from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable


@dataclass(frozen=True, slots=True)
class StripeCheckoutResult:
    session_id: str
    url: str
    expires_at: datetime
    price_id: str


class StripeGateway:
    """Small adapter around the current StripeClient service interface."""

    def __init__(self, settings: Settings) -> None:
        if not settings.billing_enabled:
            raise ProviderUnavailable("TerraSatch billing is not enabled")
        if settings.stripe_secret_key is None:
            raise ProviderUnavailable("Stripe billing credentials are not configured")
        self.settings = settings
        self.client = StripeClient(
            settings.stripe_secret_key.get_secret_value(),
            max_network_retries=2,
        )

    async def resolve_price_id(
        self,
        plan: PlanDefinition,
        interval: BillingInterval,
    ) -> str:
        lookup_key = plan.lookup_key(interval)
        if not plan.self_service or not lookup_key:
            raise InvalidConfiguration("The selected plan is not available for self-service checkout")

        try:
            prices = await asyncio.to_thread(
                self.client.v1.prices.list,
                params={"lookup_keys": [lookup_key], "active": True, "limit": 2},
            )
        except Exception as error:
            raise ProviderUnavailable("Stripe price lookup failed") from error

        matches = list(prices.data)
        if len(matches) != 1:
            raise ProviderUnavailable(
                "Stripe price catalog is not configured for this TerraSatch plan",
                details={"lookup_key": lookup_key, "matches": len(matches)},
            )
        return str(matches[0].id)

    async def create_checkout(
        self,
        *,
        signup_id: str,
        email: str,
        plan: PlanDefinition,
        interval: BillingInterval,
        expires_at: datetime,
    ) -> StripeCheckoutResult:
        price_id = await self.resolve_price_id(plan, interval)
        identifier_suffix = "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))
        metadata = {
            "product": "terrasatch",
            "billing_version": "v1",
            "signup_id": signup_id,
            "plan_code": plan.code.value,
            "billing_interval": interval.value,
        }
        params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "customer_email": email,
            "client_reference_id": signup_id,
            "payment_method_collection": "always",
            "success_url": str(self.settings.billing_success_url),
            "cancel_url": str(self.settings.billing_cancel_url),
            "expires_at": int(expires_at.timestamp()),
            "integration_identifier": f"terrasatch_{identifier_suffix}",
            "metadata": metadata,
            "subscription_data": {
                "trial_period_days": plan.trial_days,
                "metadata": metadata,
                "trial_settings": {"end_behavior": {"missing_payment_method": "cancel"}},
            },
        }
        try:
            session = await asyncio.to_thread(
                self.client.v1.checkout.sessions.create,
                params=params,
                options={"idempotency_key": f"terrasatch-signup-{signup_id}"},
            )
        except Exception as error:
            raise ProviderUnavailable("Stripe Checkout could not be created") from error

        session_id = str(session.id)
        session_url = str(session.url or "")
        if not session_id or not session_url:
            raise ProviderUnavailable("Stripe Checkout returned an incomplete session")
        checkout_expires_at = datetime.fromtimestamp(int(session.expires_at), tz=UTC)
        return StripeCheckoutResult(
            session_id=session_id,
            url=session_url,
            expires_at=checkout_expires_at,
            price_id=price_id,
        )

    async def create_customer_portal(self, *, stripe_customer_id: str) -> str:
        try:
            session = await asyncio.to_thread(
                self.client.v1.billing_portal.sessions.create,
                params={
                    "customer": stripe_customer_id,
                    "return_url": str(self.settings.billing_portal_return_url),
                },
            )
        except Exception as error:
            raise ProviderUnavailable("Stripe Customer Portal could not be created") from error
        url = str(session.url or "")
        if not url:
            raise ProviderUnavailable("Stripe Customer Portal returned an incomplete session")
        return url

    async def retrieve_subscription(self, subscription_id: str) -> dict[str, Any]:
        try:
            subscription = await asyncio.to_thread(
                self.client.v1.subscriptions.retrieve,
                subscription_id,
            )
        except Exception as error:
            raise ProviderUnavailable("Stripe subscription lookup failed") from error
        return dict(subscription.to_dict())

    def construct_event(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        if self.settings.stripe_webhook_secret is None:
            raise ProviderUnavailable("Stripe webhook secret is not configured")
        try:
            event = self.client.construct_event(
                payload.decode("utf-8"),
                signature,
                self.settings.stripe_webhook_secret.get_secret_value(),
            )
        except Exception as error:
            raise InvalidConfiguration("Stripe webhook signature validation failed") from error
        return dict(event.to_dict())
