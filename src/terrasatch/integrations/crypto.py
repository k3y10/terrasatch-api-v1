"""Encryption helpers for provider credentials stored in the TerraSatch database."""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable


def _fernet(settings: Settings) -> Fernet:
    secret = settings.integration_encryption_key
    if secret is None:
        raise ProviderUnavailable("Integration credential storage is not configured")
    try:
        return Fernet(secret.get_secret_value().encode("ascii"))
    except (UnicodeEncodeError, ValueError) as error:
        raise InvalidConfiguration("Integration encryption key is not a valid Fernet key") from error


def encrypt_payload(settings: Settings, payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _fernet(settings).encrypt(raw).decode("ascii")


def decrypt_payload(settings: Settings, encrypted_payload: str) -> dict[str, object]:
    try:
        raw = _fernet(settings).decrypt(encrypted_payload.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderUnavailable("Stored integration credentials cannot be decrypted") from error
    if not isinstance(payload, dict):
        raise ProviderUnavailable("Stored integration credentials are invalid")
    return payload
