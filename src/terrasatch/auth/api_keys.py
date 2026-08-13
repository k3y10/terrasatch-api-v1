"""API key generation and verification utilities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeneratedApiKey:
    """A newly issued raw key returned exactly once to an authorized operator."""

    token: str
    key_prefix: str
    secret_hash: str


def generate_api_key(*, environment: str) -> GeneratedApiKey:
    """Generate a high-entropy, versioned service credential and its SHA-256 digest."""

    if environment not in {"local", "development", "staging", "production"}:
        raise ValueError("Unsupported TerraSatch environment")
    mode = "live" if environment == "production" else "test"
    secret = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    token = f"ts_{mode}_{secret}"
    return GeneratedApiKey(
        token=token,
        key_prefix=token[:20],
        secret_hash=hash_api_key(token),
    )


def hash_api_key(token: str) -> str:
    """Return a non-reversible digest suitable for persistent key lookup."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_api_key(token: str, expected_hash: str) -> bool:
    """Use constant-time comparison when checking a presented API key."""

    return hmac.compare_digest(hash_api_key(token), expected_hash)