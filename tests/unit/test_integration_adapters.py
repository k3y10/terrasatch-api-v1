"""OAuth adapter, encryption, and provider-readiness tests without real provider traffic."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable
from terrasatch.integrations.adapters import (
    ArcGISOAuthAdapter,
    ConfluenceOAuthAdapter,
    GoogleCalendarOAuthAdapter,
    GoogleDriveOAuthAdapter,
    JiraOAuthAdapter,
    Microsoft365OAuthAdapter,
    MicrosoftCalendarOAuthAdapter,
    SlackOAuthAdapter,
)
from terrasatch.integrations.catalog import provider_catalog
from terrasatch.integrations.crypto import decrypt_payload, encrypt_payload
from terrasatch.integrations.provider_config import resolve_provider_app_config
from terrasatch.integrations.service import _validate_configuration


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
    assert catalog["garmin"]["support_status"] == "partner_required"
    assert catalog["garmin"]["connect_status"] == "partner_required"


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
    assert with_store["microsoft_teams"]["connect_status"] == "external_setup_required"
    assert with_store["microsoft_teams"]["can_connect"] is True
    assert with_store["webhook"]["connect_status"] == "external_setup_required"
    assert with_store["webhook"]["can_connect"] is True
    assert with_store["cloudflare_r2"]["connect_status"] == "external_setup_required"
    assert with_store["cloudflare_r2"]["can_connect"] is True
    assert with_store["aws_s3"]["connect_status"] == "external_setup_required"
    assert with_store["aws_s3"]["can_connect"] is True
    assert with_store["geojson"]["connect_status"] == "available"
    assert with_store["geojson"]["runtime_ready"] is True
    assert with_store["geojson"]["can_connect"] is True
    assert with_store["ogc_api_features"]["connect_status"] == "available"
    assert with_store["ogc_api_features"]["runtime_ready"] is True
    assert with_store["ogc_api_features"]["can_connect"] is True
    assert with_store["stac_api"]["connect_status"] == "available"
    assert with_store["stac_api"]["runtime_ready"] is True
    assert with_store["stac_api"]["can_connect"] is True
    assert with_store["arcgis_enterprise_public"]["connect_status"] == "available"
    assert with_store["arcgis_enterprise_public"]["runtime_ready"] is True
    assert with_store["arcgis_enterprise_public"]["can_connect"] is True
    assert with_store["nws_forecast"]["connect_status"] == "available"
    assert with_store["nws_forecast"]["runtime_ready"] is True
    assert with_store["nws_forecast"]["can_connect"] is True
    assert with_store["uac_forecast"]["connect_status"] == "available"
    assert with_store["uac_forecast"]["runtime_ready"] is True
    assert with_store["uac_forecast"]["can_connect"] is True


def test_operational_email_requires_platform_sender_and_resend_key() -> None:
    unavailable = {
        item["key"]: item
        for item in provider_catalog(Settings(), admin_access=True)
    }
    assert unavailable["email"]["connect_status"] == "needs_configuration"
    assert unavailable["email"]["can_connect"] is False

    available = {
        item["key"]: item
        for item in provider_catalog(
            Settings(
                resend_api_key=SecretStr("re_test_ops"),
                integration_email_from=(
                    "TerraSatch Operations <operations@terrasatch.com>"
                ),
            ),
            admin_access=True,
        )
    }
    assert available["email"]["connect_status"] == "available"
    assert available["email"]["runtime_ready"] is True
    assert available["email"]["can_connect"] is True


def test_production_operational_email_requires_exact_terrasatch_sender_domain() -> None:
    valid = Settings(
        environment="production",
        resend_api_key=SecretStr("re_test_ops"),
        integration_email_from=(
            "TerraSatch Operations <operations@terrasatch.com>"
        ),
    )
    assert valid.integration_email_is_configured is True

    lookalike = Settings(
        environment="production",
        resend_api_key=SecretStr("re_test_ops"),
        integration_email_from=(
            "TerraSatch Operations <operations@terrasatch.com.invalid>"
        ),
    )
    assert lookalike.integration_email_is_configured is False


def test_operational_email_configuration_is_allowlisted_and_normalized() -> None:
    configuration: dict[str, object] = {
        "recipients": ["OPS@Example.com", "lead@example.com"],
        "subject": "  Field   operations update  ",
    }
    _validate_configuration("email", configuration)
    assert configuration == {
        "recipients": ["ops@example.com", "lead@example.com"],
        "subject": "Field operations update",
    }

    with pytest.raises(InvalidConfiguration, match="duplicates"):
        _validate_configuration(
            "email",
            {
                "recipients": ["ops@example.com", "OPS@example.com"],
                "subject": "Field update",
            },
        )
    with pytest.raises(InvalidConfiguration, match="single-line"):
        _validate_configuration(
            "email",
            {
                "recipients": ["ops@example.com"],
                "subject": "Field update\nBcc: outsider@example.com",
            },
        )


def test_geojson_configuration_is_fixed_and_bounded() -> None:
    configuration: dict[str, object] = {
        "endpoint_url": "https://data.example.com/observations.geojson",
        "max_features": 250,
    }
    _validate_configuration("geojson", configuration)
    assert configuration == {
        "endpoint_url": "https://data.example.com/observations.geojson",
        "max_features": 250,
    }

    with pytest.raises(InvalidConfiguration, match="HTTPS URL"):
        _validate_configuration(
            "geojson",
            {
                "endpoint_url": "http://data.example.com/feed.geojson",
                "max_features": 100,
            },
        )
    with pytest.raises(InvalidConfiguration, match="between 1 and 1000"):
        _validate_configuration(
            "geojson",
            {
                "endpoint_url": "https://data.example.com/feed.geojson",
                "max_features": 1001,
            },
        )


def test_ogc_api_configuration_normalizes_allowlisted_collections() -> None:
    configuration: dict[str, object] = {
        "base_url": "https://maps.example.com/ogc/",
        "collection_ids": ["observations", "incidents-2026"],
        "max_features": 250,
    }
    _validate_configuration("ogc_api_features", configuration)
    assert configuration == {
        "base_url": "https://maps.example.com/ogc",
        "collection_ids": ["observations", "incidents-2026"],
        "max_features": 250,
    }

    with pytest.raises(InvalidConfiguration, match="duplicates"):
        _validate_configuration(
            "ogc_api_features",
            {
                "base_url": "https://maps.example.com/ogc",
                "collection_ids": ["observations", "observations"],
            },
        )
    with pytest.raises(InvalidConfiguration, match="collection ID"):
        _validate_configuration(
            "ogc_api_features",
            {
                "base_url": "https://maps.example.com/ogc",
                "collection_ids": ["../private"],
            },
        )


def test_stac_api_configuration_normalizes_allowlisted_collections() -> None:
    configuration: dict[str, object] = {
        "base_url": "https://stac.example.com/api/",
        "collection_ids": ["sentinel-2", "landsat.c2"],
        "max_items": 200,
    }
    _validate_configuration("stac_api", configuration)
    assert configuration == {
        "base_url": "https://stac.example.com/api",
        "collection_ids": ["sentinel-2", "landsat.c2"],
        "max_items": 200,
    }

    with pytest.raises(InvalidConfiguration, match="duplicates"):
        _validate_configuration(
            "stac_api",
            {
                "base_url": "https://stac.example.com/api",
                "collection_ids": ["sentinel-2", "sentinel-2"],
            },
        )
    with pytest.raises(InvalidConfiguration, match="collection ID"):
        _validate_configuration(
            "stac_api",
            {
                "base_url": "https://stac.example.com/api",
                "collection_ids": ["../private"],
            },
        )


def test_public_arcgis_enterprise_configuration_allowlists_exact_layers() -> None:
    configuration: dict[str, object] = {
        "feature_layer_urls": [
            (
                "https://gis.example.gov/server/rest/services/"
                "Avalanche/FeatureServer/0"
            ),
            (
                "https://gis.example.gov/server/rest/services/"
                "Roads/FeatureServer/2"
            ),
        ]
    }
    _validate_configuration("arcgis_enterprise_public", configuration)
    assert len(configuration["feature_layer_urls"]) == 2

    with pytest.raises(InvalidConfiguration, match="duplicates"):
        _validate_configuration(
            "arcgis_enterprise_public",
            {
                "feature_layer_urls": [
                    "https://gis.example.gov/server/rest/services/A/FeatureServer/0",
                    "https://gis.example.gov/server/rest/services/A/FeatureServer/0",
                ]
            },
        )
    with pytest.raises(InvalidConfiguration, match="FeatureServer"):
        _validate_configuration(
            "arcgis_enterprise_public",
            {
                "feature_layer_urls": [
                    "https://gis.example.gov/server/rest/services/A/MapServer/0"
                ]
            },
        )


def test_nws_forecast_configuration_bounds_period_count() -> None:
    configuration: dict[str, object] = {"max_periods": 8}
    _validate_configuration("nws_forecast", configuration)
    assert configuration == {"max_periods": 8}

    with pytest.raises(InvalidConfiguration, match="between 1 and 14"):
        _validate_configuration("nws_forecast", {"max_periods": 15})


def test_microsoft_365_configuration_supports_sharepoint_targets() -> None:
    configuration: dict[str, object] = {
        "site_id": "contoso.sharepoint.com,site-collection,site-id",
        "drive_id": "b!approved-drive",
        "folder_path": "Operations / Reports",
    }
    _validate_configuration("microsoft_365", configuration)
    assert configuration == {
        "site_id": "contoso.sharepoint.com,site-collection,site-id",
        "drive_id": "b!approved-drive",
        "folder_path": "Operations/Reports",
    }

    with pytest.raises(InvalidConfiguration, match="site_id"):
        _validate_configuration(
            "microsoft_365",
            {"site_id": "https://contoso.sharepoint.com/sites/ops"},
        )


def test_uac_configuration_normalizes_and_allowlists_regions() -> None:
    configuration: dict[str, object] = {
        "regions": ["Salt-Lake", "uintas", "moab"],
    }
    _validate_configuration("uac_forecast", configuration)
    assert configuration == {
        "regions": ["salt-lake", "uintas", "moab"],
    }

    with pytest.raises(InvalidConfiguration, match="duplicates"):
        _validate_configuration(
            "uac_forecast",
            {"regions": ["salt-lake", "Salt-Lake"]},
        )
    with pytest.raises(InvalidConfiguration, match="not supported"):
        _validate_configuration(
            "uac_forecast",
            {"regions": ["colorado"]},
        )


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
    teams_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["microsoft_teams"]["capability_details"]
    }
    assert teams_labels["notification.send"] == "Send notifications"
    webhook_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["webhook"]["capability_details"]
    }
    assert webhook_labels["notification.send"] == "Send notifications"
    email_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["email"]["capability_details"]
    }
    assert email_labels["notification.send"] == "Send notifications"
    r2_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["cloudflare_r2"]["capability_details"]
    }
    assert r2_labels["document.create"] == "Create reports and files"
    s3_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["aws_s3"]["capability_details"]
    }
    assert s3_labels["document.create"] == "Create reports and files"
    geojson_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["geojson"]["capability_details"]
    }
    assert geojson_labels["map.features.query"] == "Read map features"
    ogc_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["ogc_api_features"]["capability_details"]
    }
    assert ogc_labels["map.features.query"] == "Read map features"
    stac_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["stac_api"]["capability_details"]
    }
    assert stac_labels["map.features.query"] == "Read map features"
    enterprise_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["arcgis_enterprise_public"]["capability_details"]
    }
    assert enterprise_labels["map.features.query"] == "Read map features"
    nws_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["nws_forecast"]["capability_details"]
    }
    assert nws_labels["weather.forecast.read"] == "Read weather forecasts"
    uac_labels = {
        detail["key"]: detail["label"]
        for detail in catalog["uac_forecast"]["capability_details"]
    }
    assert uac_labels["avalanche.forecast.read"] == "Read avalanche forecasts"


def test_provider_catalog_never_offers_connect_without_secret_store() -> None:
    settings = Settings(
        integration_provider_config_json=SecretStr(
            '{"google_drive":{"client_id":"client","client_secret":"secret",'
            '"redirect_uri":"https://api.example.com/callback"}}'
        ),
    )
    catalog = {item["key"]: item for item in provider_catalog(settings)}
    assert catalog["google_drive"]["connect_status"] == "needs_configuration"
    assert catalog["google_drive"]["can_connect"] is False


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
async def test_google_calendar_oauth_uses_event_scope_and_separate_token() -> None:
    settings = Settings(
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")),
        integration_provider_config_json=SecretStr(
            '{"google_calendar":{"client_id":"google-client","client_secret":"google-secret",'
            '"redirect_uri":"https://api.example.com/google-calendar/callback"}}'
        ),
    )

    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url) == GoogleCalendarOAuthAdapter.token_endpoint:
            return httpx.Response(
                200,
                json={
                    "access_token": "calendar-access",
                    "refresh_token": "calendar-refresh",
                    "expires_in": 3600,
                    "scope": "https://www.googleapis.com/auth/calendar.events",
                    "token_type": "Bearer",
                },
            )
        if str(request.url).startswith(GoogleCalendarOAuthAdapter.events_endpoint):
            assert request.headers["Authorization"] == "Bearer calendar-access"
            return httpx.Response(200, json={"items": []})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    adapter = GoogleCalendarOAuthAdapter(
        resolve_provider_app_config(settings, "google_calendar", required=True),
        transport=httpx.MockTransport(responder),
    )
    authorization = urlparse(adapter.authorization_url(state="calendar-state"))
    params = parse_qs(authorization.query)
    assert params["scope"] == ["https://www.googleapis.com/auth/calendar.events"]
    result = await adapter.exchange_code(code="calendar-code")
    assert result.account_id == "primary"
    assert result.credentials["provider"] == "google_calendar"
    assert result.credentials["refresh_token"] == "calendar-refresh"


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



@pytest.mark.asyncio
async def test_microsoft_calendar_oauth_uses_shared_calendar_scope() -> None:
    settings = Settings(
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")),
        integration_provider_config_json=SecretStr(
            '{"microsoft_calendar":{"client_id":"ms-client","client_secret":"ms-secret",'
            '"redirect_uri":"https://api.example.com/microsoft-calendar/callback"}}'
        ),
    )

    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url) == MicrosoftCalendarOAuthAdapter.token_endpoint:
            return httpx.Response(
                200,
                json={
                    "access_token": "ms-calendar-access",
                    "refresh_token": "ms-calendar-refresh",
                    "expires_in": 3600,
                    "scope": "offline_access User.Read Calendars.ReadWrite.Shared",
                    "token_type": "Bearer",
                },
            )
        if str(request.url).startswith(MicrosoftCalendarOAuthAdapter.profile_endpoint):
            return httpx.Response(
                200,
                json={
                    "id": "user-123",
                    "displayName": "Field User",
                    "userPrincipalName": "field@example.com",
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    adapter = MicrosoftCalendarOAuthAdapter(
        resolve_provider_app_config(settings, "microsoft_calendar", required=True),
        transport=httpx.MockTransport(responder),
    )
    authorization = urlparse(adapter.authorization_url(state="ms-calendar-state"))
    params = parse_qs(authorization.query)
    assert "Calendars.ReadWrite.Shared" in params["scope"][0]
    assert "Files.ReadWrite" not in params["scope"][0]
    result = await adapter.exchange_code(code="ms-calendar-code")
    assert result.account_id == "user-123"
    assert result.credentials["provider"] == "microsoft_calendar"


@pytest.mark.asyncio
async def test_jira_oauth_uses_write_scope_and_discovers_cloud_site() -> None:
    settings = Settings(
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")),
        integration_provider_config_json=SecretStr(
            '{"jira":{"client_id":"jira-client","client_secret":"jira-secret",'
            '"redirect_uri":"https://api.example.com/jira/callback"}}'
        ),
    )

    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url) == JiraOAuthAdapter.token_endpoint:
            return httpx.Response(
                200,
                json={
                    "access_token": "jira-access",
                    "refresh_token": "jira-refresh",
                    "expires_in": 3600,
                    "scope": "offline_access write:jira-work",
                    "token_type": "Bearer",
                },
            )
        if str(request.url) == JiraOAuthAdapter.resources_endpoint:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1324a887-45db-1bf4-1e99-ef0ff456d421",
                        "name": "Field Ops",
                        "url": "https://fieldops.atlassian.net",
                        "scopes": ["write:jira-work"],
                    }
                ],
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    adapter = JiraOAuthAdapter(
        resolve_provider_app_config(settings, "jira", required=True),
        transport=httpx.MockTransport(responder),
    )
    authorization = urlparse(adapter.authorization_url(state="jira-state"))
    params = parse_qs(authorization.query)
    assert params["audience"] == ["api.atlassian.com"]
    assert "write:jira-work" in params["scope"][0]
    result = await adapter.exchange_code(code="jira-code")
    assert result.account_label == "Field Ops"
    assert result.account_id == "1324a887-45db-1bf4-1e99-ef0ff456d421"
    assert result.credentials["provider"] == "jira"


@pytest.mark.asyncio
async def test_confluence_oauth_uses_page_write_scope() -> None:
    settings = Settings(
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")),
        integration_provider_config_json=SecretStr(
            '{"confluence":{"client_id":"conf-client","client_secret":"conf-secret",'
            '"redirect_uri":"https://api.example.com/confluence/callback"}}'
        ),
    )

    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url) == ConfluenceOAuthAdapter.token_endpoint:
            return httpx.Response(
                200,
                json={
                    "access_token": "conf-access",
                    "refresh_token": "conf-refresh",
                    "expires_in": 3600,
                    "scope": "offline_access write:page:confluence",
                    "token_type": "Bearer",
                },
            )
        if str(request.url) == ConfluenceOAuthAdapter.resources_endpoint:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1324a887-45db-1bf4-1e99-ef0ff456d421",
                        "name": "Field Ops",
                        "url": "https://fieldops.atlassian.net",
                        "scopes": ["write:page:confluence"],
                    }
                ],
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    adapter = ConfluenceOAuthAdapter(
        resolve_provider_app_config(settings, "confluence", required=True),
        transport=httpx.MockTransport(responder),
    )
    authorization = urlparse(adapter.authorization_url(state="conf-state"))
    params = parse_qs(authorization.query)
    assert "write:page:confluence" in params["scope"][0]
    result = await adapter.exchange_code(code="conf-code")
    assert result.account_id == "1324a887-45db-1bf4-1e99-ef0ff456d421"
    assert result.credentials["provider"] == "confluence"


def test_atlassian_configuration_fixes_project_and_space_targets() -> None:
    jira: dict[str, object] = {
        "cloud_id": "1324a887-45db-1bf4-1e99-ef0ff456d421",
        "project_key": "ops",
        "issue_type": " Task ",
    }
    _validate_configuration("jira", jira)
    assert jira["project_key"] == "OPS"
    assert jira["issue_type"] == "Task"

    confluence: dict[str, object] = {
        "cloud_id": "1324a887-45db-1bf4-1e99-ef0ff456d421",
        "space_id": "123456",
        "parent_page_id": "654321",
    }
    _validate_configuration("confluence", confluence)
    assert confluence["space_id"] == "123456"
    assert confluence["parent_page_id"] == "654321"


def test_mapbox_managed_service_requires_fixed_style_allowlist() -> None:
    settings = Settings(
        integration_provider_config_json=SecretStr(
            '{"mapbox":{"access_token":"pk.test","username":"terrasatch",'
            '"style_ids":"field-style,incident-style"}}'
        ),
    )
    catalog = {item["key"]: item for item in provider_catalog(settings)}
    assert catalog["mapbox"]["support_status"] == "managed"
    assert catalog["mapbox"]["runtime_ready"] is True
    assert catalog["mapbox"]["connected"] is True
