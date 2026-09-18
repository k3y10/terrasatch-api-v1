from pydantic import SecretStr

from terrasatch.config import Environment, Settings


def test_billing_secrets_can_be_supplied_by_field_name_for_internal_configuration() -> None:
    settings = Settings(
        environment="production",
        billing_enabled=True,
        billing_email_webhook_url="https://example.com/api/billing-email",
        billing_email_webhook_secret=SecretStr("test-email-secret"),
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
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
        stripe_secret_key=SecretStr("sk_live_not_allowed"),
        stripe_webhook_secret=None,
    )

    assert settings.stripe_webhook_is_configured is False
    assert settings.billing_is_configured is False


def test_staging_billing_can_run_without_transactional_email() -> None:
    settings = Settings(
        environment="staging",
        billing_enabled=True,
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=None,
    )

    assert settings.billing_email_is_configured is False
    assert settings.billing_is_configured is True


def test_production_billing_still_requires_transactional_email() -> None:
    settings = Settings(
        environment="production",
        billing_enabled=True,
        billing_activation_signing_secret=SecretStr("test-activation-secret"),
        stripe_secret_key=SecretStr("sk_test_terrasatch"),
        stripe_webhook_secret=SecretStr("whsec_terrasatch"),
    )

    assert settings.billing_email_is_configured is False
    assert settings.billing_is_configured is False
