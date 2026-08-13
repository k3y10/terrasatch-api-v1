import pytest

from terrasatch.auth.api_keys import generate_api_key, verify_api_key
from terrasatch.auth.scopes import SUPPORTED_API_SCOPES, validate_api_scopes
from terrasatch.errors import InvalidConfiguration


def test_generated_production_key_is_versioned_and_only_verifies_with_its_digest() -> None:
    generated = generate_api_key(environment="production")

    assert generated.token.startswith("ts_live_")
    assert generated.key_prefix == generated.token[:20]
    assert verify_api_key(generated.token, generated.secret_hash)
    assert not verify_api_key(f"{generated.token}altered", generated.secret_hash)


def test_generated_nonproduction_key_uses_test_prefix() -> None:
    generated = generate_api_key(environment="staging")

    assert generated.token.startswith("ts_test_")


def test_supported_api_scopes_are_normalized_and_sorted() -> None:
    assert validate_api_scopes({"read:events", " admin ", "read:events"}) == [
        "admin",
        "read:events",
    ]
    assert "edge:ingest" in SUPPORTED_API_SCOPES
    assert "read:sites" in SUPPORTED_API_SCOPES
    assert "write:teams" in SUPPORTED_API_SCOPES


def test_unknown_api_scope_is_rejected() -> None:
    with pytest.raises(InvalidConfiguration, match="Unsupported API scope"):
        validate_api_scopes({"read:event"})
