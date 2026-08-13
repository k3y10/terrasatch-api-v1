from terrasatch.admin.security import (
    csrf_token_is_valid,
    generate_session_secret,
    hash_admin_password,
    issue_csrf_token,
    verify_admin_password,
)


def test_admin_password_hash_is_non_reversible_and_verifies() -> None:
    stored_hash = hash_admin_password("a-secure-admin-password")

    assert "a-secure-admin-password" not in stored_hash
    assert verify_admin_password("a-secure-admin-password", stored_hash)
    assert not verify_admin_password("incorrect-password", stored_hash)


def test_csrf_token_is_session_bound() -> None:
    session: dict[str, object] = {}
    token = issue_csrf_token(session)

    assert csrf_token_is_valid(session, token)
    assert not csrf_token_is_valid(session, "other-token")
    assert len(generate_session_secret()) >= 64