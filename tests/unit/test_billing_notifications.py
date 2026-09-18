from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

import terrasatch.billing.notifications as notifications
from terrasatch.billing.notifications import (
    BillingEmailContext,
    BillingEmailDeliveryReceipt,
    build_billing_email,
    deliver_billing_email,
    notification_kind,
)
from terrasatch.config import Settings


def context() -> BillingEmailContext:
    return BillingEmailContext(
        to="owner@example.com",
        display_name="Owner",
        organization_name="TerraSatch Test",
        plan_name="Individual",
        billing_interval="monthly",
        recurring_amount_cents=2400,
        trial_ends_at=datetime(2026, 10, 18, tzinfo=UTC),
        current_period_end=None,
        grace_ends_at=None,
        cancel_at_period_end=False,
    )


@pytest.mark.asyncio
async def test_direct_resend_delivery_uses_idempotency_and_returns_receipt(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["idempotency"] = request.headers.get("idempotency-key")
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"id": "email_terrasatch_123"})

    transport = httpx.MockTransport(responder)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        notifications.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    settings = Settings(
        resend_api_key=SecretStr("re_test_terrasatch"),
        billing_from="TerraSatch <billing@terrasatch.com>",
        billing_reply_to="support@terrasatch.com",
        billing_activation_url=(
            "https://staging-api.terrasatch.com/api/v1/workspace/billing/activate"
        ),
    )
    receipt = await deliver_billing_email(
        settings=settings,
        event_id="evt_test_123",
        kind="trial_started",
        context=context(),
        activation_token="a" * 64,
    )

    assert receipt == BillingEmailDeliveryReceipt(
        provider="resend",
        message_id="email_terrasatch_123",
    )
    assert captured["authorization"] == "Bearer re_test_terrasatch"
    assert captured["idempotency"] == "terrasatch-billing/trial_started/evt_test_123"
    body = json.loads(str(captured["body"]))
    assert body["from"] == "TerraSatch <billing@terrasatch.com>"
    assert body["to"] == ["owner@example.com"]
    assert body["reply_to"] == "support@terrasatch.com"


@pytest.mark.asyncio
async def test_direct_resend_is_preferred_over_webhook_fallback(monkeypatch) -> None:
    calls: list[str] = []

    async def direct(**_kwargs):
        calls.append("resend")
        return BillingEmailDeliveryReceipt(provider="resend", message_id="email_1")

    async def webhook(**_kwargs):
        calls.append("webhook")
        return BillingEmailDeliveryReceipt(provider="vercel_webhook", message_id=None)

    monkeypatch.setattr(notifications, "_deliver_direct_resend", direct)
    monkeypatch.setattr(notifications, "_deliver_via_webhook", webhook)

    receipt = await deliver_billing_email(
        settings=Settings(
            resend_api_key=SecretStr("re_test"),
            billing_from="TerraSatch <billing@terrasatch.com>",
            billing_email_webhook_url="https://example.com/api/billing-email",
            billing_email_webhook_secret=SecretStr("fallback"),
        ),
        event_id="evt_test_preference",
        kind="trial_ending",
        context=context(),
    )

    assert receipt is not None
    assert receipt.provider == "resend"
    assert calls == ["resend"]


def test_trial_started_message_contains_activation_and_no_card_claims() -> None:
    message = build_billing_email(
        kind="trial_started",
        context=context(),
        activation_url="https://example.com/activate#token=test",
    )

    assert "Your TerraSatch trial is active" == message.subject
    assert "Activate your account" in message.text
    assert "https://example.com/activate#token=test" in message.text
    assert "does not store card data" in message.html

def test_account_recovery_and_confirmation_messages() -> None:
    activation = build_billing_email(
        kind="activation_resend",
        context=context(),
        activation_url="https://staging-api.terrasatch.com/activate#token=test",
    )
    reset = build_billing_email(
        kind="password_reset",
        context=context(),
        activation_url="https://staging-api.terrasatch.com/portal/reset-password#token=test",
    )
    paid = build_billing_email(
        kind="payment_confirmed",
        context=context(),
        activation_url=None,
    )
    updated = build_billing_email(
        kind="subscription_updated",
        context=context(),
        activation_url=None,
    )

    assert activation.subject == "Finish setting up your TerraSatch account"
    assert "Finish setup" in activation.text
    assert reset.subject == "Reset your TerraSatch password"
    assert "single-use" in reset.text
    assert paid.subject == "TerraSatch payment received"
    assert updated.subject == "Your TerraSatch subscription was updated"


def test_notification_mapping_suppresses_zero_dollar_invoice() -> None:
    assert (
        notification_kind(
            stripe_event_type="invoice.paid",
            activation_token=None,
            context=context(),
            event_object={"amount_paid": 0},
        )
        is None
    )
    assert (
        notification_kind(
            stripe_event_type="invoice.paid",
            activation_token=None,
            context=context(),
            event_object={"amount_paid": 2400},
        )
        == "payment_confirmed"
    )


def test_subscription_update_email_requires_meaningful_previous_attributes() -> None:
    assert (
        notification_kind(
            stripe_event_type="customer.subscription.updated",
            activation_token=None,
            context=context(),
            previous_attributes={"metadata": {"example": "change"}},
        )
        is None
    )
    assert (
        notification_kind(
            stripe_event_type="customer.subscription.updated",
            activation_token=None,
            context=context(),
            previous_attributes={"items": {"data": []}},
        )
        == "subscription_updated"
    )

