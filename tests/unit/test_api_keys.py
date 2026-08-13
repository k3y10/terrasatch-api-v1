from terrasatch.auth.api_keys import generate_api_key, verify_api_key


def test_generated_production_key_is_versioned_and_only_verifies_with_its_digest() -> None:
    generated = generate_api_key(environment="production")

    assert generated.token.startswith("ts_live_")
    assert generated.key_prefix == generated.token[:20]
    assert verify_api_key(generated.token, generated.secret_hash)
    assert not verify_api_key(f"{generated.token}altered", generated.secret_hash)


def test_generated_nonproduction_key_uses_test_prefix() -> None:
    generated = generate_api_key(environment="staging")

    assert generated.token.startswith("ts_test_")