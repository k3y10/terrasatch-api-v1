"""Bootstrap administrator password and CSRF primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import MutableMapping
from typing import Any

_SCRYPT_N = 16_384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16


def hash_admin_password(password: str) -> str:
    """Create a non-reversible scrypt password representation for local configuration."""

    if len(password) < 12:
        raise ValueError("Admin password must contain at least 12 characters")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "$".join(
        (
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _encode(salt),
            _encode(digest),
        )
    )


def verify_admin_password(password: str, stored_hash: str) -> bool:
    """Verify a password against TerraSatch's fixed-cost scrypt representation."""

    try:
        algorithm, n_value, r_value, p_value, encoded_salt, encoded_digest = stored_hash.split("$")
        if algorithm != "scrypt" or (int(n_value), int(r_value), int(p_value)) != (
            _SCRYPT_N,
            _SCRYPT_R,
            _SCRYPT_P,
        ):
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(encoded_salt),
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_SCRYPT_DKLEN,
        )
        return hmac.compare_digest(digest, _decode(encoded_digest))
    except (TypeError, ValueError):
        return False


def generate_session_secret() -> str:
    """Generate a high-entropy session-signing secret for one deployment."""

    return secrets.token_urlsafe(48)


def issue_csrf_token(session: MutableMapping[str, Any]) -> str:
    """Store and return a session-bound CSRF token."""

    token = session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_token_is_valid(session: MutableMapping[str, Any], submitted_token: str | None) -> bool:
    """Use constant-time comparison for a session-bound submitted CSRF token."""

    expected_token = session.get("csrf_token")
    return isinstance(expected_token, str) and bool(submitted_token) and hmac.compare_digest(
        expected_token,
        submitted_token,
    )


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))