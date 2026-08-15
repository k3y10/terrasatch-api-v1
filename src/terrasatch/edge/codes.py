"""Pairing-code generation and hashing helpers."""
from __future__ import annotations

import hashlib
import secrets

_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_device_code() -> str:
    return secrets.token_urlsafe(32)


def hash_device_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_user_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_user_code(code: str) -> str:
    cleaned = "".join(ch for ch in code.upper() if ch.isalnum())
    if len(cleaned) != 8:
        return code.upper().strip()
    return f"{cleaned[:4]}-{cleaned[4:]}"
