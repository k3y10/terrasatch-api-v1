"""OAuth adapter, encryption, and provider-readiness tests without real provider traffic."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from terrasatch.config import Settings
from terrasatch.errors import ProviderUnavailable
from terrasatch.integrations.adapters import GoogleDriveOAuthAdapter, SlackOAuthAdapter
from terrasatch.integrations.catalog import provider_catalog
from terrasatch.integrations.crypto import decrypt_payload, encrypt_payload


def configured_settings() -> Settings:
    return Settings(
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")),
        google_oauth_client_id="google-client",
        google_oauth_client_secret=SecretStr("google-secret"),
        google_oauth_redirect_uri=(
            "https://api.example.com/api/v1/workspace/"
            "integrations/oauth/google_drive/callback"
        ),
        slack_oauth_client_id="slack-client",
        slack_oauth_client_secret=SecretStr("slack-secret"),
        slack_oauth_redirect_uri=(
            "https://api.example.com/api/v1/workspace/"
            "integrations/oauth/slack/callback"
        ),
    )


def test_provider_catalog_only_marks_server_configured_oauth_as_available() -> None:
    planned = {item["key"]: item["setup_status"] for item in provider_catalog(Settings())}
    assert planned["google_drive"] == "planned"
    assert planned["slack"] == "planned"
    available = {
        item["key"]: item["setup_status"]
        for item in provider_catalog(configured_settings())
    }
    assert available["google_drive"] == "available"
    assert available["slack"] == "available"
    assert available["garmin"] == "planned"


def test_invalid_integration_encryption_key_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError, match="integration encryption key"):
        Settings(integration_encryption_key=SecretStr("not-a-fernet-key"))


def test_provider_credentials_are_encrypted_at_rest() -> None:
    settings = configured_settings()
    payload = {"access_token": "secret-token", "refresh_token": "secret-refresh"}
    encrypted = encrypt_payload(settings, payload)
    assert "secret-token" not in encrypted
    assert decrypt_payload(settings, encrypted) == payload


@pytest.mark.asyncio
async def test_google_drive_oauth_uses_narrow_drive_file_scope_and_probes_identity() -> None:
    settings = configured_settings()
    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url) == GoogleDriveOAuthAdapter.token_endpoint:
            return httpx.Response(
                200,
                json={
                    "access_token": "google-access",
                    "refresh_token": "google-refresh",
                    "expires_in": 3600,
                    "scope": "https://www.googleapis.com/auth/drive.file",
                    "token_type": "Bearer",
                },
            )
        if str(request.url).startswith(GoogleDriveOAuthAdapter.about_endpoint):
            assert request.headers["Authorization"] == "Bearer google-access"
            return httpx.Response(
                200,
                json={
                    "user": {
                        "displayName": "Field User",
                        "emailAddress": "field@example.com",
                        "permissionId": "permission-123",
                    }
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")
    adapter = GoogleDriveOAuthAdapter(settings, transport=httpx.MockTransport(responder))
    authorization = urlparse(adapter.authorization_url(state="state-value"))
    params = parse_qs(authorization.query)
    assert authorization.hostname == "accounts.google.com"
    assert params["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert params["access_type"] == ["offline"]
    assert params["state"] == ["state-value"]
    result = await adapter.exchange_code(code="authorization-code")
    assert result.account_label == "field@example.com"
    assert result.account_id == "permission-123"
    assert result.credentials["refresh_token"] == "google-refresh"


@pytest.mark.asyncio
async def test_slack_oauth_requests_incoming_webhook_and_stores_destination_metadata() -> None:
    settings = configured_settings()
    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url) == SlackOAuthAdapter.token_endpoint:
            assert request.headers.get("Authorization", "").startswith("Basic ")
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "access_token": "xoxb-test",
                    "token_type": "bot",
                    "scope": "incoming-webhook",
                    "team": {"name": "Field Ops", "id": "T123"},
                    "incoming_webhook": {
                        "channel": "#field-ops",
                        "channel_id": "C123",
                        "configuration_url": "https://slack.example/config",
                        "url": "https://hooks.slack.com/services/secret",
                    },
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")
    adapter = SlackOAuthAdapter(settings, transport=httpx.MockTransport(responder))
    authorization = urlparse(adapter.authorization_url(state="slack-state"))
    params = parse_qs(authorization.query)
    assert authorization.hostname == "slack.com"
    assert params["scope"] == ["incoming-webhook"]
    assert params["state"] == ["slack-state"]
    result = await adapter.exchange_code(code="slack-code")
    assert result.account_label == "Field Ops"
    assert result.account_id == "T123"
    assert result.credentials["incoming_webhook"]["channel_id"] == "C123"



@pytest.mark.asyncio
async def test_slack_oauth_rejects_install_without_approved_webhook_destination() -> None:
    settings = configured_settings()

    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url) == SlackOAuthAdapter.token_endpoint:
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "access_token": "xoxb-test",
                    "token_type": "bot",
                    "scope": "incoming-webhook",
                    "team": {"name": "Field Ops", "id": "T123"},
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    adapter = SlackOAuthAdapter(
        settings,
        transport=httpx.MockTransport(responder),
    )
    with pytest.raises(ProviderUnavailable, match="webhook destination"):
        await adapter.exchange_code(code="slack-code")


@pytest.mark.asyncio
async def test_slack_revocation_refreshes_rotated_token_before_remote_revoke() -> None:
    settings = configured_settings()
    calls: list[tuple[str, str]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if str(request.url) == SlackOAuthAdapter.token_endpoint:
            body = request.content.decode("utf-8")
            assert "grant_type=refresh_token" in body
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "access_token": "xoxe.xoxb-rotated",
                    "refresh_token": "xoxe-refresh-2",
                    "expires_in": 43200,
                    "scope": "incoming-webhook",
                    "token_type": "bot",
                },
            )
        if str(request.url) == SlackOAuthAdapter.revoke_endpoint:
            assert request.headers["Authorization"] == "Bearer xoxe.xoxb-rotated"
            return httpx.Response(200, json={"ok": True, "revoked": True})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    adapter = SlackOAuthAdapter(
        settings,
        transport=httpx.MockTransport(responder),
    )
    await adapter.revoke(
        {
            "provider": "slack",
            "access_token": "xoxe.xoxb-expired",
            "refresh_token": "xoxe-refresh-1",
            "expires_at": "2000-01-01T00:00:00+00:00",
            "incoming_webhook": {
                "channel": "#field-ops",
                "channel_id": "C123",
                "url": "https://hooks.slack.com/services/T/B/secret",
            },
        }
    )
    assert calls == [
        ("POST", SlackOAuthAdapter.token_endpoint),
        ("POST", SlackOAuthAdapter.revoke_endpoint),
    ]
