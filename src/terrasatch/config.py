"""Central, validated application configuration."""

from __future__ import annotations

from base64 import urlsafe_b64decode
from binascii import Error as BinasciiError
from email.utils import parseaddr
from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import (
    AliasChoices,
    AnyHttpUrl,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    field_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Settings loaded from environment variables and an optional local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TERRASATCH_",
        extra="ignore",
    )

    environment: Environment = Field(
        default=Environment.LOCAL,
        validation_alias=AliasChoices(
            "environment",
            "TERRASATCH_ENV",
            "TERRASATCH_ENVIRONMENT",
        ),
    )
    deployment_name: str = Field(default="local", min_length=1, max_length=64)
    build_sha: str = Field(default="unknown", min_length=1, max_length=64)
    api_base_url: AnyHttpUrl = "http://localhost:8000"
    database_url: PostgresDsn = (
        "postgresql+asyncpg://terrasatch:terrasatch@localhost:5432/terrasatch"
    )
    redis_url: RedisDsn = "redis://localhost:6379/0"
    log_level: str = "INFO"
    log_format: str = "json"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    enable_docs: bool = True
    stt_provider: str = "local_whisper"
    intelligence_provider: str = "deterministic"
    ollama_base_url: AnyHttpUrl = "http://127.0.0.1:11434"
    ollama_model: str = Field(default="qwen3:1.7b", min_length=1, max_length=128)
    intelligence_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    intelligence_fallback_to_deterministic: bool = True
    storage_provider: str = "local_filesystem"
    uac_archive_path: str | None = None

    # External provider integrations. Provider credentials stay server-side; browser clients
    # receive only connection metadata and authorization destinations.
    integration_encryption_key: SecretStr | None = None
    integration_provider_config_json: SecretStr | None = None
    integration_encryption_key_id: str = Field(default="v1", min_length=1, max_length=64)
    integration_oauth_state_ttl_minutes: int = Field(default=10, ge=3, le=30)
    integration_return_url: AnyHttpUrl = "https://terrasatch.com/workspace?view=Integrations"
    google_oauth_client_id: str | None = Field(default=None, max_length=512)
    google_oauth_client_secret: SecretStr | None = None
    google_oauth_redirect_uri: AnyHttpUrl | None = None
    slack_oauth_client_id: str | None = Field(default=None, max_length=512)
    slack_oauth_client_secret: SecretStr | None = None
    slack_oauth_redirect_uri: AnyHttpUrl | None = None
    arcgis_oauth_client_id: str | None = Field(default=None, max_length=512)
    arcgis_oauth_client_secret: SecretStr | None = None
    arcgis_oauth_redirect_uri: AnyHttpUrl | None = None
    integration_email_from: str | None = Field(default=None, max_length=320)
    integration_email_reply_to: str | None = Field(default=None, max_length=320)

    # Billing stays disabled until the separate TerraSatch Stripe account is explicitly configured.
    billing_enabled: bool = False
    # Live-mode Stripe webhooks remain a separate explicit production safety gate.
    billing_allow_livemode: bool = False
    billing_grace_days: int = Field(default=7, ge=1, le=30)
    billing_checkout_ttl_minutes: int = Field(default=120, ge=30, le=1440)
    billing_activation_ttl_hours: int = Field(default=24, ge=1, le=168)
    account_password_reset_ttl_minutes: int = Field(default=30, ge=10, le=120)
    billing_success_url: str = Field(
        default="https://terrasatch.com/billing/success?session_id={CHECKOUT_SESSION_ID}",
        min_length=10,
        max_length=1000,
    )
    billing_cancel_url: str = Field(
        default="https://terrasatch.com/#cost",
        min_length=10,
        max_length=1000,
    )
    billing_portal_return_url: str = Field(
        default="https://api.terrasatch.com/portal",
        min_length=10,
        max_length=1000,
    )
    billing_activation_url: str = Field(
        default="https://terrasatch.com/activate",
        min_length=10,
        max_length=1000,
    )
    billing_staging_trust_caddy_stripe_ips: bool = False
    billing_staging_individual_payment_link_url: str | None = None
    billing_staging_individual_payment_link_id: str | None = None
    billing_staging_team_payment_link_url: str | None = None
    billing_staging_team_payment_link_id: str | None = None
    # Primary transactional email path: direct Resend delivery from the durable Oracle outbox.
    # The protected Vercel webhook below remains a fallback for deployments that do not
    # provide Resend credentials directly to the API/worker.
    resend_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "resend_api_key",
            "TERRASATCH_RESEND_API_KEY",
            "RESEND_API_KEY",
        ),
    )
    resend_webhook_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "resend_webhook_secret",
            "TERRASATCH_RESEND_WEBHOOK_SECRET",
            "RESEND_WEBHOOK_SECRET",
        ),
    )
    billing_from: str | None = Field(default=None, max_length=320)
    billing_reply_to: str | None = Field(default=None, max_length=320)
    billing_email_webhook_url: AnyHttpUrl | None = None
    billing_email_webhook_secret: SecretStr | None = None
    billing_activation_signing_secret: SecretStr | None = None
    stripe_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "stripe_secret_key",
            "TERRASATCH_STRIPE_SECRET_KEY",
            "STRIPE_SECRET_KEY",
        ),
    )
    stripe_webhook_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "stripe_webhook_secret",
            "TERRASATCH_STRIPE_WEBHOOK_SECRET",
            "STRIPE_WEBHOOK_SECRET",
        ),
    )

    max_edge_devices: int = Field(default=100, ge=1, le=100_000)
    max_portal_users: int = Field(default=250, ge=1, le=1_000_000)
    admin_email: str | None = None
    admin_password_hash: SecretStr | None = None
    admin_session_secret: SecretStr | None = None
    admin_session_max_age_seconds: int = Field(default=28_800, ge=900, le=86_400)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return [origin.strip().rstrip("/") for origin in value]

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("build_sha")
    @classmethod
    def normalize_build_sha(cls, value: str) -> str:
        return value.strip() or "unknown"

    @field_validator(
        "billing_from",
        "billing_reply_to",
        "integration_email_from",
        "integration_email_reply_to",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator(
        "resend_api_key",
        "resend_webhook_secret",
        "stripe_secret_key",
        "stripe_webhook_secret",
        "billing_email_webhook_secret",
        "billing_activation_signing_secret",
        "integration_encryption_key",
        "integration_provider_config_json",
        "google_oauth_client_secret",
        "slack_oauth_client_secret",
        "arcgis_oauth_client_secret",
        mode="before",
    )
    @classmethod
    def normalize_optional_secret(cls, value):
        if value is None:
            return None
        if isinstance(value, SecretStr):
            raw = value.get_secret_value().strip()
            return SecretStr(raw) if raw else None
        raw = str(value).strip()
        return raw or None

    @field_validator("integration_encryption_key")
    @classmethod
    def validate_integration_encryption_key(
        cls,
        value: SecretStr | None,
    ) -> SecretStr | None:
        if value is None:
            return None
        try:
            decoded = urlsafe_b64decode(value.get_secret_value().encode("ascii"))
        except (BinasciiError, UnicodeEncodeError, ValueError) as error:
            raise ValueError("integration encryption key must be a Fernet key") from error
        if len(decoded) != 32:
            raise ValueError("integration encryption key must decode to 32 bytes")
        return value

    @field_validator("uac_archive_path")
    @classmethod
    def normalize_uac_archive_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def admin_is_configured(self) -> bool:
        """Expose browser administration when signed browser sessions are configured.

        Database-backed superadmin users are the primary administrators. The legacy
        admin email/password hash remain optional bootstrap and break-glass credentials.
        """

        return self.admin_session_secret is not None

    @property
    def integration_secret_store_is_configured(self) -> bool:
        """Return whether encrypted provider credential storage is enabled."""

        return self.integration_encryption_key is not None

    @property
    def google_drive_oauth_is_configured(self) -> bool:
        """Return whether the Google Drive web-server OAuth flow can be started."""

        return bool(
            self.integration_secret_store_is_configured
            and self.google_oauth_client_id
            and self.google_oauth_client_secret
            and self.google_oauth_redirect_uri
        )

    @property
    def slack_oauth_is_configured(self) -> bool:
        """Return whether the Slack OAuth v2 flow can be started."""

        return bool(
            self.integration_secret_store_is_configured
            and self.slack_oauth_client_id
            and self.slack_oauth_client_secret
            and self.slack_oauth_redirect_uri
        )

    @property
    def arcgis_oauth_is_configured(self) -> bool:
        """Return whether the ArcGIS Online server-side OAuth flow can be started."""

        return bool(
            self.integration_secret_store_is_configured
            and self.arcgis_oauth_client_id
            and self.arcgis_oauth_client_secret
            and self.arcgis_oauth_redirect_uri
        )

    @property
    def staging_payment_links_are_configured(self) -> bool:
        """Return whether isolated staging can use Stripe-hosted sandbox Payment Links."""

        return bool(
            self.environment == Environment.STAGING
            and not self.billing_allow_livemode
            and self.billing_staging_trust_caddy_stripe_ips
            and self.billing_staging_individual_payment_link_url
            and self.billing_staging_individual_payment_link_id
            and self.billing_staging_team_payment_link_url
            and self.billing_staging_team_payment_link_id
        )

    @property
    def stripe_webhook_is_configured(self) -> bool:
        """Require HMAC in production; allow tightly scoped sandbox verification in staging."""

        if self.stripe_webhook_secret is not None:
            return True
        if (
            self.environment == Environment.STAGING
            and not self.billing_allow_livemode
            and self.stripe_secret_key is not None
        ):
            secret = self.stripe_secret_key.get_secret_value()
            if secret.startswith(("sk_test_", "rk_test_")):
                return True
        return self.staging_payment_links_are_configured

    @staticmethod
    def _sender_uses_terrasatch_domain(value: str) -> bool:
        _display_name, address = parseaddr(value)
        if not address or "@" not in address:
            return False
        _local_part, domain = address.rsplit("@", 1)
        return domain.casefold() == "terrasatch.com"

    @staticmethod
    def _sender_uses_terrasatch_domain(value: str) -> bool:
        _display_name, address = parseaddr(value)
        if not address or "@" not in address:
            return False
        _local_part, domain = address.rsplit("@", 1)
        return domain.casefold() == "terrasatch.com"

    @property
    def integration_email_sender(self) -> str | None:
        """Return the operational sender, falling back to the verified billing sender."""

        return self.integration_email_from or self.billing_from

    @property
    def integration_email_is_configured(self) -> bool:
        """Return whether TerraSatch can send approved operational email through Resend."""

        sender = self.integration_email_sender
        if not self.resend_api_key or not sender:
            return False
        if self.environment in {Environment.STAGING, Environment.PRODUCTION}:
            return self._sender_uses_terrasatch_domain(sender)
        return True

    @property
    def billing_resend_is_configured(self) -> bool:
        """Return whether Oracle can send transactional email directly through Resend."""

        if not self.resend_api_key or not self.billing_from:
            return False
        if self.environment in {Environment.STAGING, Environment.PRODUCTION}:
            return "@terrasatch.com" in self.billing_from.casefold()
        return True

    @property
    def resend_webhook_is_configured(self) -> bool:
        """Return whether Resend delivery events can be signature-verified."""

        return self.resend_webhook_secret is not None

    @property
    def billing_email_webhook_is_configured(self) -> bool:
        """Return whether the protected Vercel billing-email fallback is configured."""

        return bool(self.billing_email_webhook_url and self.billing_email_webhook_secret)

    @property
    def billing_email_is_configured(self) -> bool:
        """Return whether at least one durable transactional email path is configured."""

        return bool(
            self.billing_resend_is_configured
            or self.billing_email_webhook_is_configured
        )

    @property
    def billing_is_configured(self) -> bool:
        """Require billing safety primitives; production additionally requires email delivery."""

        provider_ready = bool(self.stripe_secret_key or self.staging_payment_links_are_configured)
        core_ready = bool(
            self.billing_enabled
            and provider_ready
            and self.stripe_webhook_is_configured
            and self.billing_activation_signing_secret
        )
        if not core_ready:
            return False
        if self.environment in {Environment.STAGING, Environment.PRODUCTION}:
            return bool(
                self.billing_resend_is_configured
                and self.resend_webhook_is_configured
            )
        return self.billing_email_is_configured


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
