"""Central provider application configuration resolver.

Customer connection credentials live in integration_credentials. This module resolves only
TerraSatch's platform-level provider application configuration (OAuth client identity and callback).
A single secret bundle is preferred so adding providers does not require expanding the deployment
environment indefinitely. Legacy per-provider settings remain as a compatibility fallback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable


@dataclass(frozen=True, slots=True)
class ProviderAppConfig:
    provider_key: str
    client_id: str
    client_secret: str
    redirect_uri: str
    source: str


_LEGACY_FIELDS: dict[str, tuple[str, str, str]] = {
    "google_drive": (
        "google_oauth_client_id",
        "google_oauth_client_secret",
        "google_oauth_redirect_uri",
    ),
    "slack": (
        "slack_oauth_client_id",
        "slack_oauth_client_secret",
        "slack_oauth_redirect_uri",
    ),
    "esri_arcgis": (
        "arcgis_oauth_client_id",
        "arcgis_oauth_client_secret",
        "arcgis_oauth_redirect_uri",
    ),
}


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    normalized = str(value).strip()
    return normalized or None


def _validate_redirect_uri(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.fragment:
        raise InvalidConfiguration("Provider redirect_uri must be an absolute HTTP(S) URL")
    return value


def _bundle(settings: Settings) -> dict[str, object]:
    secret = settings.integration_provider_config_json
    if secret is None:
        return {}
    try:
        payload = json.loads(secret.get_secret_value())
    except (TypeError, ValueError) as error:
        raise InvalidConfiguration(
            "Integration provider config bundle must contain valid JSON"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidConfiguration(
            "Integration provider config bundle must be a JSON object"
        )
    return payload


def resolve_provider_app_config(
    settings: Settings,
    provider_key: str,
    *,
    required: bool = False,
) -> ProviderAppConfig | None:
    """Resolve platform provider config without exposing it through catalog responses."""

    raw = _bundle(settings).get(provider_key)
    if raw is not None:
        if not isinstance(raw, dict):
            raise InvalidConfiguration(
                f"Provider config for {provider_key} must be a JSON object"
            )
        allowed = {"client_id", "client_secret", "redirect_uri"}
        unexpected = sorted(set(raw) - allowed)
        if unexpected:
            raise InvalidConfiguration(
                f"Unsupported provider config fields for {provider_key}: "
                + ", ".join(unexpected)
            )
        client_id = _clean_text(raw.get("client_id"))
        client_secret = _clean_text(raw.get("client_secret"))
        redirect_uri = _clean_text(raw.get("redirect_uri"))
        if not client_id or not client_secret or not redirect_uri:
            raise InvalidConfiguration(
                f"Provider config for {provider_key} is incomplete"
            )
        return ProviderAppConfig(
            provider_key=provider_key,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=_validate_redirect_uri(redirect_uri),
            source="bundle",
        )

    legacy = _LEGACY_FIELDS.get(provider_key)
    if legacy is not None:
        client_id = _clean_text(getattr(settings, legacy[0], None))
        client_secret = _clean_text(getattr(settings, legacy[1], None))
        redirect_uri = _clean_text(getattr(settings, legacy[2], None))
        if client_id and client_secret and redirect_uri:
            return ProviderAppConfig(
                provider_key=provider_key,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=_validate_redirect_uri(redirect_uri),
                source="legacy_settings",
            )

    if required:
        raise ProviderUnavailable(
            f"{provider_key} platform authorization is not configured"
        )
    return None


def provider_app_is_configured(settings: Settings, provider_key: str) -> bool:
    if not settings.integration_secret_store_is_configured:
        return False
    try:
        return resolve_provider_app_config(settings, provider_key) is not None
    except InvalidConfiguration:
        return False


def resolve_provider_secret_fields(
    settings: Settings,
    provider_key: str,
    *,
    required_fields: set[str],
    required: bool = False,
) -> dict[str, str] | None:
    """Resolve non-OAuth platform secrets from the central provider bundle."""

    raw = _bundle(settings).get(provider_key)
    if raw is None:
        if required:
            raise ProviderUnavailable(
                f"{provider_key} platform service configuration is not configured"
            )
        return None
    if not isinstance(raw, dict):
        raise InvalidConfiguration(
            f"Provider config for {provider_key} must be a JSON object"
        )

    unexpected = sorted(set(raw) - required_fields)
    if unexpected:
        raise InvalidConfiguration(
            f"Unsupported provider config fields for {provider_key}: "
            + ", ".join(unexpected)
        )

    resolved: dict[str, str] = {}
    for field in required_fields:
        value = _clean_text(raw.get(field))
        if not value:
            raise InvalidConfiguration(
                f"Provider config for {provider_key} is missing {field}"
            )
        resolved[field] = value
    return resolved


def provider_secret_is_configured(
    settings: Settings,
    provider_key: str,
    *,
    required_fields: set[str],
) -> bool:
    try:
        return (
            resolve_provider_secret_fields(
                settings,
                provider_key,
                required_fields=required_fields,
            )
            is not None
        )
    except InvalidConfiguration:
        return False
