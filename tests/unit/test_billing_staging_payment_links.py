from __future__ import annotations

import pytest
from pydantic import SecretStr

from terrasatch.api.billing import _validate_staging_payment_link_event
from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable


def staging_settings() -> Settings:
    return Settings(
        environment="staging",
        billing_enabled=True,
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        billing_staging_trust_caddy_stripe_ips=True,
        billing_staging_individual_payment_link_url="https://buy.stripe.com/test_individual",
        billing_staging_individual_payment_link_id="plink_individual",
        billing_staging_team_payment_link_url="https://buy.stripe.com/test_team",
        billing_staging_team_payment_link_id="plink_team",
    )


def checkout_event(*, link: str = "plink_individual", plan: str = "field") -> dict[str, object]:
    return {
        "id": "evt_test_checkout",
        "type": "checkout.session.completed",
        "livemode": False,
        "data": {
            "object": {
                "id": "cs_test_checkout",
                "mode": "subscription",
                "payment_link": link,
                "client_reference_id": "72bd85dc-0c07-4f90-8277-809767438422",
                "metadata": {
                    "product": "terrasatch",
                    "billing_version": "v2",
                    "environment": "staging",
                    "plan_code": plan,
                    "billing_interval": "monthly",
                },
            }
        },
    }


def test_staging_payment_link_checkout_event_is_strictly_scoped() -> None:
    _validate_staging_payment_link_event(
        settings=staging_settings(),
        event=checkout_event(),
    )


@pytest.mark.parametrize(
    ("link", "plan"),
    [
        ("plink_unknown", "field"),
        ("plink_individual", "team"),
    ],
)
def test_staging_payment_link_checkout_rejects_wrong_link_or_plan(
    link: str,
    plan: str,
) -> None:
    with pytest.raises(InvalidConfiguration):
        _validate_staging_payment_link_event(
            settings=staging_settings(),
            event=checkout_event(link=link, plan=plan),
        )


def test_staging_payment_link_webhook_rejects_livemode_event() -> None:
    event = checkout_event()
    event["livemode"] = True

    with pytest.raises(ProviderUnavailable):
        _validate_staging_payment_link_event(
            settings=staging_settings(),
            event=event,
        )


def test_staging_subscription_event_requires_terrasatch_metadata() -> None:
    event = {
        "id": "evt_test_subscription",
        "type": "customer.subscription.created",
        "livemode": False,
        "data": {
            "object": {
                "id": "sub_test",
                "metadata": {
                    "product": "other",
                    "billing_version": "v2",
                    "environment": "staging",
                    "plan_code": "field",
                    "billing_interval": "monthly",
                },
            }
        },
    }

    with pytest.raises(InvalidConfiguration):
        _validate_staging_payment_link_event(
            settings=staging_settings(),
            event=event,
        )
