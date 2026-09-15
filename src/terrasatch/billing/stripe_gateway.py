"""Stripe Billing gateway isolated from TerraSatch domain state."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from terrasatch.billing.plans import BillingInterval, PlanDefinition
from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable

_STRIPE_API_BASE = "https://api.stripe.com/v1"
_WEBHOOK_TOLERANCE_SECONDS = 300


@dataclass(frozen=True, slots=True)
class StripeCheckoutResult:
    session_id: str
    url: str
    expires_at: datetime
    price_id: str


class StripeGateway:
    """Small Stripe REST adapter using the API's existing HTTP client dependency."""

    def __init__(self, settings: Settings) -> None:
        if not settings.billing_enabled:
            raise ProviderUnavailable("TerraSatch billing is not enabled")
        if settings.stripe_secret_key is None:
            raise ProviderUnavailable("Stripe billing credentials are not configured")
        self.settings = settings
        self.secret_key = settings.stripe_secret_key.get_secret_value()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "User-Agent": "TerraSatch-Billing/1.0",
        }

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, str]] | dict[str, str] | None = None,
        data: list[tuple[str, str]] | dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = dict(self._headers)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.request(
                    method,
                    f"{_STRIPE_API_BASE}{path}",
                    headers=headers,
                    params=params,
                    data=data,
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ProviderUnavailable("Stripe API request failed") from error
        if not isinstance(payload, dict):
            raise ProviderUnavailable("Stripe API returned an invalid response")
        return payload

    async def resolve_price_id(
        self,
        plan: PlanDefinition,
        interval: BillingInterval,
    ) -> str:
        lookup_key = plan.lookup_key(interval)
        if not plan.self_service or not lookup_key:
            raise InvalidConfiguration("The selected plan is not available for self-service checkout")

        payload = await self._request_json(
            "GET",
            "/prices",
            params=[
                ("lookup_keys[]", lookup_key),
                ("active", "true"),
                ("limit", "2"),
            ],
        )
        raw_data = payload.get("data")
        matches = raw_data if isinstance(raw_data, list) else []
        if len(matches) != 1 or not isinstance(matches[0], dict) or not matches[0].get("id"):
            raise ProviderUnavailable(
                "Stripe price catalog is not configured for this TerraSatch plan",
                details={"lookup_key": lookup_key, "matches": len(matches)},
            )
        return str(matches[0]["id"])

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
        data: list[tuple[str, str]] = [
            ("mode", "subscription"),
            ("line_items[0][price]", price_id),
            ("line_items[0][quantity]", "1"),
            ("customer_email", email),
            ("client_reference_id", signup_id),
            ("payment_method_collection", "always"),
            ("success_url", str(self.settings.billing_success_url)),
            ("cancel_url", str(self.settings.billing_cancel_url)),
            ("expires_at", str(int(expires_at.timestamp()))),
            ("integration_identifier", f"terrasatch_{identifier_suffix}"),
            ("subscription_data[trial_period_days]", str(plan.trial_days)),
            (
                "subscription_data[trial_settings][end_behavior][missing_payment_method]",
                "cancel",
            ),
        ]
        for key, value in metadata.items():
            data.append((f"metadata[{key}]", value))
            data.append((f"subscription_data[metadata][{key}]", value))

        session = await self._request_json(
            "POST",
            "/checkout/sessions",
            data=data,
            idempotency_key=f"terrasatch-signup-{signup_id}",
        )
        session_id = str(session.get("id") or "")
        session_url = str(session.get("url") or "")
        expires_value = session.get("expires_at")
        try:
            checkout_expires_at = datetime.fromtimestamp(int(expires_value), tz=UTC)
        except (TypeError, ValueError, OSError) as error:
            raise ProviderUnavailable("Stripe Checkout returned an invalid expiration") from error
        if not session_id or not session_url:
            raise ProviderUnavailable("Stripe Checkout returned an incomplete session")
        return StripeCheckoutResult(
            session_id=session_id,
            url=session_url,
            expires_at=checkout_expires_at,
            price_id=price_id,
        )

    async def create_customer_portal(self, *, stripe_customer_id: str) -> str:
        session = await self._request_json(
            "POST",
            "/billing_portal/sessions",
            data={
                "customer": stripe_customer_id,
                "return_url": str(self.settings.billing_portal_return_url),
            },
        )
        url = str(session.get("url") or "")
        if not url:
            raise ProviderUnavailable("Stripe Customer Portal returned an incomplete session")
        return url

    async def retrieve_subscription(self, subscription_id: str) -> dict[str, Any]:
        if not subscription_id.startswith("sub_"):
            raise InvalidConfiguration("Stripe subscription ID is invalid")
        return await self._request_json("GET", f"/subscriptions/{subscription_id}")

    def construct_event(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        """Verify Stripe's signed webhook payload without introducing a second HTTP SDK."""

        if self.settings.stripe_webhook_secret is None:
            raise ProviderUnavailable("Stripe webhook secret is not configured")
        timestamp: int | None = None
        signatures: list[str] = []
        for component in signature.split(","):
            key, separator, value = component.strip().partition("=")
            if not separator:
                continue
            if key == "t" and timestamp is None:
                try:
                    timestamp = int(value)
                except ValueError:
                    timestamp = None
            elif key == "v1" and value:
                signatures.append(value)
        if timestamp is None or not signatures:
            raise InvalidConfiguration("Stripe webhook signature validation failed")

        now = int(datetime.now(UTC).timestamp())
        if abs(now - timestamp) > _WEBHOOK_TOLERANCE_SECONDS:
            raise InvalidConfiguration("Stripe webhook signature validation failed")

        secret = self.settings.stripe_webhook_secret.get_secret_value().encode("utf-8")
        signed_payload = str(timestamp).encode("ascii") + b"." + payload
        expected = hmac.new(secret, signed_payload, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
            raise InvalidConfiguration("Stripe webhook signature validation failed")

        try:
            event = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidConfiguration("Stripe webhook payload is invalid JSON") from error
        if not isinstance(event, dict):
            raise InvalidConfiguration("Stripe webhook payload is invalid")
        return event
