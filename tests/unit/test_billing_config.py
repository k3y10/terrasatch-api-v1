from pydantic import SecretStr

from terrasatch.config import Environment, Settings


def test_billing_secrets_can_be_supplied_by_field_name_for_internal_configuration() -> None:
    settings = Settings(
        environment="production",
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        resend_webhook_secret=SecretStr("whsec_resend"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=SecretStr("whsec_terrasatch"),
    )

    assert settings.environment == Environment.PRODUCTION
    assert settings.is_production is True
    assert settings.stripe_secret_key is not None
    assert settings.stripe_secret_key.get_secret_value() == "sk_test_terrasatch"
    assert settings.stripe_webhook_secret is not None
    assert settings.stripe_webhook_secret.get_secret_value() == "whsec_terrasatch"
    assert settings.billing_is_configured is True


def test_billing_remains_unconfigured_without_explicit_enablement() -> None:
    settings = Settings(
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=SecretStr("whsec_terrasatch"),
    )

    assert settings.billing_enabled is False
    assert settings.billing_allow_livemode is False
    assert settings.billing_is_configured is False


def test_staging_can_verify_test_webhooks_by_event_retrieval_without_signing_secret() -> None:
    settings = Settings(
        environment="staging",
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        resend_webhook_secret=SecretStr("whsec_resend"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=None,
    )

    assert settings.stripe_webhook_is_configured is True
    assert settings.billing_is_configured is True


def test_production_still_requires_webhook_signing_secret() -> None:
    settings = Settings(
        environment="production",
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=None,
    )

    assert settings.stripe_webhook_is_configured is False
    assert settings.billing_is_configured is False


def test_staging_retrieval_verification_rejects_live_stripe_keys() -> None:
    settings = Settings(
        environment="staging",
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        resend_webhook_secret=SecretStr("whsec_resend"),
        stripe_secret_key=SecretStr("sk_live_not_allowed"),
        stripe_webhook_secret=None,
    )

    assert settings.stripe_webhook_is_configured is False
    assert settings.billing_is_configured is False


def test_staging_billing_requires_transactional_email_and_reconciliation() -> None:
    settings = Settings(
        environment="staging",
        billing_enabled=True,
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=None,
    )

    assert settings.billing_email_is_configured is False
    assert settings.resend_webhook_is_configured is False
    assert settings.billing_is_configured is False


def test_production_billing_still_requires_transactional_email() -> None:
    settings = Settings(
        environment="production",
        billing_enabled=True,
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        resend_webhook_secret=SecretStr("whsec_resend"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=SecretStr("whsec_terrasatch"),
    )

    assert settings.billing_email_is_configured is False
    assert settings.billing_is_configured is False


def test_staging_payment_links_can_run_without_any_stripe_api_secret() -> None:
    settings = Settings(
        environment="staging",
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
        resend_webhook_secret=SecretStr("whsec_resend"),
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        billing_staging_trust_caddy_stripe_ips=True,
        billing_staging_individual_payment_link_url="https://buy.stripe.com/test_individual",
        billing_staging_individual_payment_link_id="plink_individual",
        billing_staging_team_payment_link_url="https://buy.stripe.com/test_team",
        billing_staging_team_payment_link_id="plink_team",
    )

    assert settings.stripe_secret_key is None
    assert settings.staging_payment_links_are_configured is True
    assert settings.stripe_webhook_is_configured is True
    assert settings.billing_email_is_configured is True
    assert settings.resend_webhook_is_configured is True
    assert settings.billing_is_configured is True


def test_payment_link_mode_cannot_enable_production_billing() -> None:
    settings = Settings(
        environment="production",
        billing_enabled=True,
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        billing_staging_trust_caddy_stripe_ips=True,
        billing_staging_individual_payment_link_url="https://buy.stripe.com/test_individual",
        billing_staging_individual_payment_link_id="plink_individual",
        billing_staging_team_payment_link_url="https://buy.stripe.com/test_team",
        billing_staging_team_payment_link_id="plink_team",
    )

    assert settings.staging_payment_links_are_configured is False
    assert settings.billing_is_configured is False


def test_direct_resend_satisfies_transactional_email_readiness() -> None:
    settings = Settings(
        environment="production",
        billing_enabled=True,
        resend_api_key=SecretStr("re_test_terrasatch"),
        resend_webhook_secret=SecretStr("whsec_resend"),
        billing_from="TerraSatch <billing@terrasatch.com>",
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=SecretStr("whsec_terrasatch"),
    )

    assert settings.billing_resend_is_configured is True
    assert settings.billing_email_webhook_is_configured is False
    assert settings.billing_email_is_configured is True
    assert settings.billing_is_configured is True


def test_webhook_fallback_still_satisfies_email_readiness() -> None:
    settings = Settings(
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
    )

    assert settings.billing_resend_is_configured is False
    assert settings.billing_email_webhook_is_configured is True
    assert settings.billing_email_is_configured is True


def test_empty_email_and_stripe_secrets_are_normalized_to_none() -> None:
    settings = Settings(
        resend_api_key="   ",
        resend_webhook_secret="",
        billing_email_webhook_secret="",
        billing_activation_signing_secret=" ",
        stripe_secret_key="",
        stripe_webhook_secret=" ",
        billing_from=" ",
        billing_reply_to=" ",
    )

    assert settings.resend_api_key is None
    assert settings.resend_webhook_secret is None
    assert settings.billing_email_webhook_secret is None
    assert settings.billing_activation_signing_secret is None
    assert settings.stripe_secret_key is None
    assert settings.stripe_webhook_secret is None
    assert settings.billing_from is None
    assert settings.billing_reply_to is None
    assert settings.billing_email_is_configured is False


def test_local_billing_requires_email_sender_but_not_resend_delivery_webhook() -> None:
    settings = Settings(
        environment="local",
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=SecretStr("whsec_terrasatch"),
    )

    assert settings.billing_email_is_configured is True
    assert settings.resend_webhook_is_configured is False
    assert settings.billing_is_configured is True


def test_staging_requires_resend_delivery_webhook_reconciliation() -> None:
    settings = Settings(
        environment="staging",
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=None,
    )

    assert settings.billing_email_is_configured is True
    assert settings.resend_webhook_is_configured is False
    assert settings.billing_is_configured is False


def test_production_requires_resend_delivery_webhook_reconciliation() -> None:
    settings = Settings(
        environment="production",
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=SecretStr("whsec_terrasatch"),
    )

    assert settings.billing_email_is_configured is True
    assert settings.resend_webhook_is_configured is False
    assert settings.billing_is_configured is False
