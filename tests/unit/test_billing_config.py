from pydantic import SecretStr

from terrasatch.config import Environment, Settings


def test_billing_secrets_can_be_supplied_by_field_name_for_internal_configuration() -> None:
    settings = Settings(
        environment="production",
        billing_enabled=True,
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
