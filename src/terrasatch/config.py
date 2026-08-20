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
    billing_enabled: bool = False
    max_edge_devices: int = Field(default=100, ge=1, le=100_000)
    max_portal_users: int = Field(default=250, ge=1, le=1_000_000)
    admin_email: str | None = None
    admin_password_hash: SecretStr | None = None
    admin_session_secret: SecretStr | None = None
    admin_session_max_age_seconds: int = Field(default=28_800, ge=900, le=86_400)

    # flaikConnect is a server-to-server integration. Keep all values private and
    # leave disabled unless an authorized Snowbird environment is configured.
    flaik_mode: str = Field(default="disabled", pattern="^(disabled|fixture|live)$")
    flaik_auth_url: AnyHttpUrl | None = None
    flaik_api_base_url: AnyHttpUrl | None = None
    flaik_client_id: str | None = Field(default=None, max_length=512)
    flaik_client_secret: SecretStr | None = None
    flaik_scope: str = Field(default="flaik.connect.api.read", min_length=1, max_length=256)
    flaik_classes_path: str | None = Field(default=None, max_length=512)
    flaik_timekeeping_path: str | None = Field(default=None, max_length=512)
    flaik_timeout_seconds: float = Field(default=8.0, ge=1.0, le=60.0)
    flaik_enrich_transmissions: bool = False

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

    @field_validator("flaik_client_id", "flaik_classes_path", "flaik_timekeeping_path", mode="before")
    @classmethod
    def normalize_optional_flaik_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def admin_is_configured(self) -> bool:
        """Only expose browser administration when all required secrets are configured."""

        return bool(self.admin_email and self.admin_password_hash and self.admin_session_secret)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
