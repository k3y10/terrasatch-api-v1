"""OAuth adapter, encryption, and provider-readiness tests without real provider traffic."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from terrasatch.config import Settings
from terrasatch.errors import ProviderUnavailable
from terrasatch.integrations.adapters import (
    ArcGISOAuthAdapter,
    GoogleDriveOAuthAdapter,
    Microsoft365OAuthAdapter,
    SlackOAuthAdapter,
)
from terrasatch.integrations.catalog import provider_catalog
from terrasatch.integrations.crypto import decrypt_payload, encrypt_payload
from terrasatch.integrations.provider_config import resolve_provider_app_config


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
        arcgis_oauth_client_id="arcgis-client",
        arcgis_oauth_client_secret=SecretStr("arcgis-secret"),
        arcgis_oauth_redirect_uri=(
            "https://api.example.com/api/v1/workspace/"
            "integrations/oauth/esri_arcgis/callback"
        ),
    )


def test_provider_catalog_only_marks_server_configured_oauth_as_available() -> None:
    planned = {item["key"]: item["setup_status"] for item in provider_catalog(Settings())}
    assert planned["google_drive"] == "planned"
    assert planned["slack"] == "planned"
    assert planned["esri_arcgis"] == "planned"
    available = {
        item["key"]: item["setup_status"]
        for item in provider_catalog(configured_settings())
    }
    assert available["google_drive"] == "available"
    assert available["slack"] == "available"
    assert available["esri_arcgis"] == "available"
    assert available["garmin"] == "planned"

    catalog = {
        item["key"]: item
        for item in provider_catalog(
            configured_settings(),
            admin_access=False,
            connected_scopes={"google_drive": {"user"}},
        )
    }
    assert catalog["google_drive"]["support_status"] == "supported"
    assert catalog["google_drive"]["connect_status"] == "available"
    assert catalog["google_drive"]["allowed_scopes"] == ["user"]
    assert catalog["google_drive"]["connected"] is True
    assert catalog["google_drive"]["connected_scopes"] == ["user"]
    assert catalog["slack"]["allowed"] is False
    assert catalog["slack"]["requires_admin"] is True
    assert catalog["garmin"]["support_status"] == "coming_soon"
    assert catalog["garmin"]["connect_status"] == "coming_soon"


def test_manual_provider_requires_encrypted_credential_store() -> None:
    without_store = {
        item["key"]: item
        for item in provider_catalog(Settings(), admin_access=True)
    }
    assert without_store["snowflake"]["support_status"] == "supported"
    assert without_store["snowflake"]["connect_status"] == "needs_configuration"
    assert without_store["snowflake"]["can_connect"] is False

    with_store = {
        item["key"]: item
        for item in provider_catalog(
            Settings(
                integration_encryption_key=SecretStr(
                    Fernet.generate_key().decode("ascii")
                )
            ),
            admin_access=True,
        )
    }
    assert with_store["snowflake"]["connect_status"] == "external_setup_required"
    assert with_store["snowflake"]["can_connect"] is True


def test_provider_config_bundle_replaces_per_provider_env_sprawl() -> None:
    settings = Settings(
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")),
        integration_provider_config_json=SecretStr(
            '{"slack":{"client_id":"bundle-client","client_secret":"bundle-secret",'
            '"redirect_uri":"https://api.example.com/callback"}}'
        ),
        slack_oauth_client_id="legacy-client",
        slack_oauth_client_secret=SecretStr("legacy-secret"),
        slack_oauth_redirect_uri="https://legacy.example.com/callback",
    )
    resolved = resolve_provider_app_config(settings, "slack", required=True)
    assert resolved is not None
    assert resolved.client_id == "bundle-client"
    assert resolved.client_secret == "bundle-secret"
    assert resolved.redirect_uri == "https://api.example.com/callback"
    assert resolved.source == "bundle"


def test_provider_catalog_labels_runtime_capabilities_for_people() -> None:
    catalog = {item["key"]: item for item in provider_catalog(configured_settings())}
    labels = {
        detail["key"]: detail["label"]
        for detail in catalog["google_drive"]["capability_details"]
    }
    assert labels["document.create"] == "Create reports and files"
    slack_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["slack"]["capability_details"]
    }
    assert slack_labels["notification.send"] == "Send notifications"


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
    adapter = GoogleDriveOAuthAdapter(
        resolve_provider_app_config(settings, "google_drive", required=True),
        transport=httpx.MockTransport(responder),
    )
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
    adapter = SlackOAuthAdapter(
        resolve_provider_app_config(settings, "slack", required=True),
        transport=httpx.MockTransport(responder),
    )
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
        resolve_provider_app_config(settings, "slack", required=True),
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
        resolve_provider_app_config(settings, "slack", required=True),
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


@pytest.mark.asyncio
async def test_arcgis_oauth_exchanges_refreshable_user_token_and_probes_identity() -> None:
    settings = configured_settings()

    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url) == ArcGISOAuthAdapter.token_endpoint:
            body = request.content.decode("utf-8")
            assert "grant_type=authorization_code" in body
            assert "client_secret=arcgis-secret" in body
            return httpx.Response(
                200,
                json={
                    "access_token": "arcgis-access",
                    "refresh_token": "arcgis-refresh",
                    "expires_in": 1800,
                    "refresh_token_expires_in": 604800,
                    "username": "field_user",
                },
            )
        if str(request.url).startswith(ArcGISOAuthAdapter.self_endpoint):
            assert request.headers["Authorization"] == "Bearer arcgis-access"
            return httpx.Response(
                200,
                json={
                    "username": "field_user",
                    "fullName": "Field User",
                    "orgId": "ORG123",
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    adapter = ArcGISOAuthAdapter(
        resolve_provider_app_config(settings, "esri_arcgis", required=True),
        transport=httpx.MockTransport(responder),
    )
    authorization = urlparse(adapter.authorization_url(state="arcgis-state"))
    params = parse_qs(authorization.query)
    assert authorization.hostname == "www.arcgis.com"
    assert params["response_type"] == ["code"]
    assert params["state"] == ["arcgis-state"]

    result = await adapter.exchange_code(code="arcgis-code")
    assert result.account_label == "Field User"
    assert result.account_id == "ORG123:field_user"
    assert result.credentials["refresh_token"] == "arcgis-refresh"


@pytest.mark.asyncio
async def test_arcgis_revoke_invalidates_refresh_token() -> None:
    settings = configured_settings()

    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == ArcGISOAuthAdapter.revoke_endpoint
        body = request.content.decode("utf-8")
        assert "auth_token=arcgis-refresh" in body
        assert "token_type_hint=refresh_token" in body
        assert "client_id=arcgis-client" in body
        return httpx.Response(200, json={"success": True})

    adapter = ArcGISOAuthAdapter(
        resolve_provider_app_config(settings, "esri_arcgis", required=True),
        transport=httpx.MockTransport(responder),
    )
    await adapter.revoke(
        {
            "access_token": "arcgis-access",
            "refresh_token": "arcgis-refresh",
        }
    )


@pytest.mark.asyncio
async def test_microsoft_oauth_requests_one_drive_scopes_and_probes_identity() -> None:
    settings = Settings(
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")),
        integration_provider_config_json=SecretStr(
            '{"microsoft_365":{"client_id":"ms-client","client_secret":"ms-secret",'
            '"redirect_uri":"https://api.example.com/microsoft/callback"}}'
        ),
    )

    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url) == Microsoft365OAuthAdapter.token_endpoint:
            return httpx.Response(
                200,
                json={
                    "access_token": "ms-access",
                    "refresh_token": "ms-refresh",
                    "expires_in": 3600,
                    "scope": "offline_access User.Read Files.ReadWrite",
                    "token_type": "Bearer",
                },
            )
        if str(request.url).startswith(Microsoft365OAuthAdapter.profile_endpoint):
            assert request.headers["Authorization"] == "Bearer ms-access"
            return httpx.Response(
                200,
                json={
                    "id": "user-123",
                    "displayName": "Field User",
                    "userPrincipalName": "field@example.com",
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    adapter = Microsoft365OAuthAdapter(
        resolve_provider_app_config(settings, "microsoft_365", required=True),
        transport=httpx.MockTransport(responder),
    )
    authorization = urlparse(adapter.authorization_url(state="ms-state"))
    params = parse_qs(authorization.query)
    assert authorization.hostname == "login.microsoftonline.com"
    assert "Files.ReadWrite" in params["scope"][0]
    assert "offline_access" in params["scope"][0]
    result = await adapter.exchange_code(code="ms-code")
    assert result.account_id == "user-123"
    assert result.credentials["refresh_token"] == "ms-refresh"
