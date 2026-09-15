"""Central, validated application configuration."""

from __future__ import annotations

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
        validation_alias=AliasChoices("TERRASATCH_ENV", "TERRASATCH_ENVIRONMENT"),
    )
    deployment_name: str = Field(default="local", min_length=1, max_length=64)
    build_sha: str = Field(default="unknown", min_length=1, max_length=64)
    api_base_url: AnyHttpUrl = "http://localhost:8000"
    database_url: PostgresDsn = "postgresql+asyncpg://terrasatch:terrasatch@localhost:5432/terrasatch"
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

    # Billing stays disabled until the separate TerraSatch Stripe account is explicitly configured.
    billing_enabled: bool = False
    # Live-mode Stripe webhooks remain a separate explicit production safety gate.
    billing_allow_livemode: bool = False
    billing_grace_days: int = Field(default=7, ge=1, le=30)
    billing_checkout_ttl_minutes: int = Field(default=120, ge=30, le=1440)
    billing_activation_ttl_hours: int = Field(default=24, ge=1, le=168)
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
    billing_email_webhook_url: AnyHttpUrl | None = None
    billing_email_webhook_secret: SecretStr | None = None
    stripe_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("TERRASATCH_STRIPE_SECRET_KEY", "STRIPE_SECRET_KEY"),
    )
    stripe_webhook_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("TERRASATCH_STRIPE_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET"),
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
        """Only expose browser administration when all required secrets are configured."""

        return bool(self.admin_email and self.admin_password_hash and self.admin_session_secret)

    @property
    def billing_is_configured(self) -> bool:
        """Return true only when billing is enabled and Stripe secrets are present."""

        return bool(self.billing_enabled and self.stripe_secret_key and self.stripe_webhook_secret)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
