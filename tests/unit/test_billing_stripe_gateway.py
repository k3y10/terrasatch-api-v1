from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from terrasatch.billing.plans import BillingInterval, PlanCode, get_plan
from terrasatch.billing.stripe_gateway import StripeGateway
from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="billing-stripe-gateway-test",
        billing_enabled=True,
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=SecretStr("whsec_terrasatch_test"),
    )


class RecordingStripeGateway(StripeGateway):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.request: dict[str, object] | None = None

    async def resolve_price_id(self, plan, interval):  # type: ignore[no-untyped-def]
        assert plan.code == PlanCode.FIELD
        assert interval == BillingInterval.MONTHLY
        return "price_field_monthly_test"

    async def _request_json(  # type: ignore[override]
        self,
        method: str,
        path: str,
        *,
        params=None,
        data=None,
        idempotency_key=None,
    ) -> dict[str, object]:
        self.request = {
            "method": method,
            "path": path,
            "params": params,
            "data": data,
            "idempotency_key": idempotency_key,
        }
        assert data is not None
        return {
            "id": "cs_test_terrasatch",
            "url": "https://checkout.stripe.com/c/pay/cs_test_terrasatch",
            "expires_at": data["expires_at"],
        }


@pytest.mark.asyncio
async def test_checkout_uses_lookup_price_and_server_owned_subscription_metadata() -> None:
    gateway = RecordingStripeGateway(make_settings())
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    result = await gateway.create_checkout(
        signup_id="3f0dcb44-2b7f-4f62-9005-613c6aee28ca",
        email="operator@example.com",
        plan=get_plan(PlanCode.FIELD),
        interval=BillingInterval.MONTHLY,
        expires_at=expires_at,
    )

    assert result.session_id == "cs_test_terrasatch"
    assert result.price_id == "price_field_monthly_test"
    assert gateway.request is not None
    assert gateway.request["method"] == "POST"
    assert gateway.request["path"] == "/checkout/sessions"
    assert gateway.request["idempotency_key"] == (
        "terrasatch-signup-3f0dcb44-2b7f-4f62-9005-613c6aee28ca"
    )
    data = gateway.request["data"]
    assert isinstance(data, dict)
    assert data["mode"] == "subscription"
    assert data["line_items[0][price]"] == "price_field_monthly_test"
    assert data["payment_method_collection"] == "always"
    assert data["subscription_data[trial_period_days]"] == "30"
    assert data["metadata[product]"] == "terrasatch"
    assert data["metadata[plan_code]"] == "field"
    assert data["subscription_data[metadata][plan_code]"] == "field"
    assert "payment_method" not in data
    assert "card" not in " ".join(data)


def test_construct_event_accepts_current_valid_stripe_signature() -> None:
    settings = make_settings()
    gateway = StripeGateway(settings)
    payload = json.dumps(
        {
            "id": "evt_test_terrasatch",
            "type": "invoice.paid",
            "livemode": False,
            "data": {"object": {"id": "in_test_terrasatch"}},
        },
        separators=(",", ":"),
    ).encode()
    timestamp = int(datetime.now(UTC).timestamp())
    expected = hmac.new(
        settings.stripe_webhook_secret.get_secret_value().encode(),
        str(timestamp).encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()

    event = gateway.construct_event(
        payload=payload,
        signature=f"t={timestamp},v1={expected}",
    )

    assert event["id"] == "evt_test_terrasatch"
    assert event["type"] == "invoice.paid"


def test_construct_event_rejects_invalid_stripe_signature() -> None:
    gateway = StripeGateway(make_settings())
    payload = b'{"id":"evt_test_bad"}'
    timestamp = int(datetime.now(UTC).timestamp())

    with pytest.raises(InvalidConfiguration, match="signature validation failed"):
        gateway.construct_event(
            payload=payload,
            signature=f"t={timestamp},v1=not-a-valid-signature",
        )
