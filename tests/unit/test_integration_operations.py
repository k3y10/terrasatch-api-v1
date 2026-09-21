"""Provider output primitive tests with no live external traffic."""

import base64
import json
from uuid import uuid4

import httpx
import pytest

from terrasatch.errors import InvalidConfiguration, ProviderUnavailable
from terrasatch.integrations.operations import (
    create_google_calendar_event,
    create_google_drive_file,
    create_microsoft_calendar_event,
    create_microsoft_drive_file,
    probe_aws_s3_bucket,
    probe_cloudflare_r2_bucket,
    probe_nws_api,
    put_aws_s3_object,
    put_cloudflare_r2_object,
    query_arcgis_features,
    query_caltopo_map,
    query_geojson_features,
    query_nws_forecast,
    query_ogc_features,
    query_public_arcgis_features,
    query_snowflake,
    query_stac_items,
    read_mapbox_style,
    send_resend_notification,
    send_slack_message,
    send_teams_message,
    send_webhook_notification,
    validate_aws_region,
    validate_generic_webhook_url,
    validate_geojson_url,
    validate_nws_forecast_url,
    validate_ogc_api_base_url,
    validate_public_arcgis_feature_layer_destination,
    validate_public_arcgis_feature_layer_url,
    validate_public_geojson_destination,
    validate_public_ogc_destination,
    validate_public_stac_destination,
    validate_public_webhook_destination,
    validate_r2_endpoint_url,
    validate_stac_api_base_url,
    validate_teams_workflow_url,
)


@pytest.mark.asyncio
async def test_operational_email_uses_fixed_recipients_and_idempotency() -> None:
    connection_id = uuid4()
    request_id = uuid4()

    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.resend.com/emails"
        assert request.headers["Authorization"] == "Bearer re_test_ops"
        assert request.headers["Idempotency-Key"] == (
            f"terrasatch-email/{connection_id}/{request_id}"
        )
        payload = json.loads(request.content)
        assert payload == {
            "from": "TerraSatch Operations <operations@terrasatch.com>",
            "to": ["ops@example.com", "lead@example.com"],
            "subject": "Field operations update",
            "text": "Field update",
            "reply_to": "support@terrasatch.com",
        }
        return httpx.Response(200, json={"id": "email_ops_123"})

    result = await send_resend_notification(
        api_key="re_test_ops",
        sender="TerraSatch Operations <operations@terrasatch.com>",
        recipients=["ops@example.com", "lead@example.com"],
        subject="Field operations update",
        text="Field update",
        request_id=request_id,
        connection_id=connection_id,
        reply_to="support@terrasatch.com",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "email_ops_123"
    assert result.metadata == {
        "provider": "resend",
        "recipient_count": 2,
    }


@pytest.mark.asyncio
async def test_slack_webhook_posts_only_to_the_oauth_destination() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://hooks.slack.com/services/T/B/secret"
        assert json.loads(request.content) == {"text": "Field update"}
        return httpx.Response(200, text="ok")

    result = await send_slack_message(
        {
            "incoming_webhook": {
                "url": "https://hooks.slack.com/services/T/B/secret",
                "channel": "#field",
                "channel_id": "C123",
            }
        },
        text="Field update",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "C123"
    assert result.metadata == {"channel": "#field", "channel_id": "C123"}


@pytest.mark.asyncio
async def test_slack_webhook_rejects_untrusted_destination() -> None:
    with pytest.raises(InvalidConfiguration, match="destination"):
        await send_slack_message(
            {
                "incoming_webhook": {
                    "url": "https://evil.example.com/services/T/B/secret",
                }
            },
            text="Do not send",
        )


@pytest.mark.asyncio
async def test_teams_workflows_webhook_uses_adaptive_card_payload() -> None:
    url = (
        "https://prod-01.westus.logic.azure.com/workflows/"
        "abc/triggers/manual/paths/invoke?api-version=2016-10-01&sig=test"
    )

    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == url
        payload = json.loads(request.content)
        assert payload["type"] == "message"
        card = payload["attachments"][0]["content"]
        assert card["type"] == "AdaptiveCard"
        assert card["body"][0]["text"] == "Field update"
        return httpx.Response(202, headers={"x-ms-workflow-run-id": "run-123"})

    result = await send_teams_message(
        {"webhook_url": url},
        text="Field update",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "run-123"
    assert result.metadata["status_code"] == 202


def test_teams_workflows_webhook_rejects_non_microsoft_host() -> None:
    with pytest.raises(InvalidConfiguration, match="destination"):
        validate_teams_workflow_url(
            "https://example.com/workflows/abc/triggers/manual/paths/invoke?sig=test"
        )


@pytest.mark.asyncio
async def test_generic_webhook_signs_payload_and_sends_idempotency_key() -> None:
    request_id = uuid4()

    def responder(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload == {
            "request_id": str(request_id),
            "text": "Field update",
            "type": "terrasatch.notification",
            "version": "1",
        }
        assert request.headers["Idempotency-Key"] == str(request_id)
        assert request.headers["X-TerraSatch-Event"] == "notification.send"
        assert request.headers["X-TerraSatch-Signature"].startswith("sha256=")
        assert request.headers["X-TerraSatch-Timestamp"]
        return httpx.Response(204, headers={"x-request-id": "receiver-1"})

    result = await send_webhook_notification(
        {
            "webhook_url": "https://ops.example.com/terrasatch/events",
            "signing_secret": "shared-secret",
        },
        text="Field update",
        request_id=request_id,
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "receiver-1"
    assert result.metadata["signed"] is True


def test_generic_webhook_rejects_local_and_ip_destinations() -> None:
    for url in (
        "https://localhost/hook",
        "https://127.0.0.1/hook",
        "https://service.internal/hook",
    ):
        with pytest.raises(InvalidConfiguration):
            validate_generic_webhook_url(url)


@pytest.mark.asyncio
async def test_generic_webhook_rejects_private_dns_resolution(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [
            (
                2,
                1,
                6,
                "",
                ("169.254.169.254", 443),
            )
        ]

    monkeypatch.setattr("terrasatch.integrations.operations.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(InvalidConfiguration, match="non-public address"):
        await validate_public_webhook_destination(
            "https://hooks.example.com/terrasatch",
            label="Generic",
        )


@pytest.mark.asyncio
async def test_generic_webhook_accepts_public_dns_resolution(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [
            (
                2,
                1,
                6,
                "",
                ("93.184.216.34", 443),
            )
        ]

    monkeypatch.setattr("terrasatch.integrations.operations.socket.getaddrinfo", fake_getaddrinfo)
    assert (
        await validate_public_webhook_destination(
            "https://hooks.example.com/terrasatch",
            label="Generic",
        )
        == "https://hooks.example.com/terrasatch"
    )


@pytest.mark.asyncio
async def test_geojson_query_returns_bounded_feature_collection() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://data.example.com/observations.geojson"
        assert request.headers["Accept"] == "application/geo+json, application/json"
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "bbox": [-112.0, 40.0, -111.0, 41.0],
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-111.8, 40.6]},
                        "properties": {"name": "A"},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-111.7, 40.7]},
                        "properties": {"name": "B"},
                    },
                ],
            },
        )

    result = await query_geojson_features(
        endpoint_url="https://data.example.com/observations.geojson",
        max_features=1,
        transport=httpx.MockTransport(responder),
    )
    assert result.data["type"] == "FeatureCollection"
    assert len(result.data["features"]) == 1
    assert result.metadata == {
        "source_host": "data.example.com",
        "feature_count": 1,
        "source_feature_count": 2,
        "truncated": True,
    }


def test_geojson_url_rejects_query_credentials_and_ip_literal() -> None:
    for url in (
        "https://data.example.com/feed.geojson?token=secret",
        "https://user:pass@data.example.com/feed.geojson",
        "https://127.0.0.1/feed.geojson",
    ):
        with pytest.raises(InvalidConfiguration):
            validate_geojson_url(url)


@pytest.mark.asyncio
async def test_geojson_rejects_private_dns_resolution(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [(2, 1, 6, "", ("10.0.0.8", 443))]

    monkeypatch.setattr(
        "terrasatch.integrations.operations.socket.getaddrinfo",
        fake_getaddrinfo,
    )
    with pytest.raises(InvalidConfiguration, match="non-public address"):
        await validate_public_geojson_destination(
            "https://data.example.com/feed.geojson"
        )


@pytest.mark.asyncio
async def test_geojson_streaming_limit_rejects_large_response() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * 5_000_001,
            headers={"Content-Type": "application/geo+json"},
        )

    with pytest.raises(ProviderUnavailable, match="size limit"):
        await query_geojson_features(
            endpoint_url="https://data.example.com/feed.geojson",
            max_features=100,
            transport=httpx.MockTransport(responder),
        )


@pytest.mark.asyncio
async def test_ogc_features_query_uses_only_core_parameters() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(
            "https://maps.example.com/ogc/collections/observations/items?"
        )
        params = dict(request.url.params)
        assert params == {
            "limit": "25",
            "bbox": "-112.0,40.0,-111.0,41.0",
            "datetime": "2026-09-20T00:00:00Z/2026-09-21T00:00:00Z",
        }
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "numberMatched": 40,
                "numberReturned": 1,
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-111.8, 40.6]},
                        "properties": {"name": "Observation"},
                    }
                ],
            },
        )

    result = await query_ogc_features(
        base_url="https://maps.example.com/ogc",
        collection_id="observations",
        limit=25,
        bbox=[-112, 40, -111, 41],
        datetime_value="2026-09-20T00:00:00Z/2026-09-21T00:00:00Z",
        transport=httpx.MockTransport(responder),
    )
    assert result.metadata["collection_id"] == "observations"
    assert result.metadata["feature_count"] == 1
    assert result.metadata["number_matched"] == 40


def test_ogc_api_rejects_unsafe_base_url() -> None:
    with pytest.raises(InvalidConfiguration, match="without credentials"):
        validate_ogc_api_base_url("https://user:pass@maps.example.com/ogc")


@pytest.mark.asyncio
async def test_ogc_api_rejects_private_dns_resolution(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [(2, 1, 6, "", ("192.168.1.8", 443))]

    monkeypatch.setattr(
        "terrasatch.integrations.operations.socket.getaddrinfo",
        fake_getaddrinfo,
    )
    with pytest.raises(InvalidConfiguration, match="non-public address"):
        await validate_public_ogc_destination("https://maps.example.com/ogc")


@pytest.mark.asyncio
async def test_ogc_api_rejects_invalid_bbox_and_datetime() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"type": "FeatureCollection", "features": []},
        )
    )
    with pytest.raises(InvalidConfiguration, match="WGS84"):
        await query_ogc_features(
            base_url="https://maps.example.com/ogc",
            collection_id="observations",
            limit=10,
            bbox=[-200, 40, -111, 41],
            transport=transport,
        )
    with pytest.raises(InvalidConfiguration, match="datetime"):
        await query_ogc_features(
            base_url="https://maps.example.com/ogc",
            collection_id="observations",
            limit=10,
            datetime_value="not-a-date",
            transport=transport,
        )


@pytest.mark.asyncio
async def test_aws_s3_bucket_probe_uses_regional_virtual_host_and_sigv4() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        assert str(request.url) == (
            "https://field-reports.s3.us-west-2.amazonaws.com/"
        )
        assert "/us-west-2/s3/aws4_request" in request.headers["Authorization"]
        assert request.headers["x-amz-content-sha256"] == (
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        )
        return httpx.Response(200)

    result = await probe_aws_s3_bucket(
        {
            "access_key_id": "aws-access",
            "secret_access_key": "aws-secret",
        },
        region="us-west-2",
        bucket="field-reports",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "field-reports"
    assert result.metadata["region"] == "us-west-2"
    assert result.metadata["endpoint_host"] == (
        "field-reports.s3.us-west-2.amazonaws.com"
    )


@pytest.mark.asyncio
async def test_aws_s3_put_supports_temporary_session_credentials() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert str(request.url) == (
            "https://field-reports.s3.us-east-1.amazonaws.com/"
            "exports/shift-report.txt"
        )
        assert request.content == b"Shift report"
        assert request.headers["x-amz-security-token"] == "session-token"
        assert "x-amz-security-token" in request.headers["Authorization"]
        return httpx.Response(200, headers={"etag": '"aws-etag"'})

    result = await put_aws_s3_object(
        {
            "access_key_id": "aws-access",
            "secret_access_key": "aws-secret",
            "session_token": "session-token",
        },
        region="us-east-1",
        bucket="field-reports",
        prefix="exports",
        name="shift-report.txt",
        content="Shift report",
        mime_type="text/plain",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "exports/shift-report.txt"
    assert result.metadata["etag"] == '"aws-etag"'


def test_aws_s3_region_rejects_unsupported_partition() -> None:
    with pytest.raises(InvalidConfiguration, match="region"):
        validate_aws_region("cn-north-1")


@pytest.mark.asyncio
async def test_r2_bucket_probe_uses_sigv4_auto_region() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        assert str(request.url) == (
            "https://abc123.r2.cloudflarestorage.com/field-reports"
        )
        assert "/auto/s3/aws4_request" in request.headers["Authorization"]
        assert request.headers["x-amz-content-sha256"] == (
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        )
        return httpx.Response(200)

    result = await probe_cloudflare_r2_bucket(
        {
            "access_key_id": "r2-access",
            "secret_access_key": "r2-secret",
        },
        endpoint_url="https://abc123.r2.cloudflarestorage.com",
        bucket="field-reports",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "field-reports"
    assert result.metadata["endpoint_host"] == "abc123.r2.cloudflarestorage.com"


@pytest.mark.asyncio
async def test_r2_document_create_puts_only_the_approved_object() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert str(request.url) == (
            "https://abc123.r2.cloudflarestorage.com/"
            "field-reports/exports/shift-report.txt"
        )
        assert request.content == b"Shift report"
        assert request.headers["Content-Type"] == "text/plain"
        assert "/auto/s3/aws4_request" in request.headers["Authorization"]
        return httpx.Response(200, headers={"etag": '"etag-123"'})

    result = await put_cloudflare_r2_object(
        {
            "access_key_id": "r2-access",
            "secret_access_key": "r2-secret",
        },
        endpoint_url="https://abc123.r2.cloudflarestorage.com",
        bucket="field-reports",
        prefix="exports",
        name="shift-report.txt",
        content="Shift report",
        mime_type="text/plain",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "exports/shift-report.txt"
    assert result.metadata["bucket"] == "field-reports"
    assert result.metadata["etag"] == '"etag-123"'


def test_r2_endpoint_rejects_non_cloudflare_s3_destination() -> None:
    with pytest.raises(InvalidConfiguration, match="R2 endpoint"):
        validate_r2_endpoint_url("https://storage.example.com")


@pytest.mark.asyncio
async def test_drive_export_uses_multipart_upload_and_optional_parent() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.googleapis.com"
        assert request.url.path == "/upload/drive/v3/files"
        assert request.url.params["uploadType"] == "multipart"
        assert request.url.params["supportsAllDrives"] == "true"
        assert request.headers["Authorization"] == "Bearer google-access"
        body = request.content.decode("utf-8")
        assert '"name":"shift-report.txt"' in body
        assert '"mimeType":"text/plain"' in body
        assert '"parents":["folder-123"]' in body
        assert "Shift report" in body
        return httpx.Response(
            200,
            json={
                "id": "file-123",
                "name": "shift-report.txt",
                "mimeType": "text/plain",
                "webViewLink": "https://drive.google.com/file/d/file-123/view",
            },
        )

    result = await create_google_drive_file(
        {"access_token": "google-access"},
        name="shift-report.txt",
        content="Shift report",
        mime_type="text/plain",
        folder_id="folder-123",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "file-123"
    assert result.metadata["name"] == "shift-report.txt"


@pytest.mark.asyncio
async def test_arcgis_feature_query_uses_bearer_auth_and_post_body() -> None:
    layer_url = (
        "https://services3.arcgis.com/ORG/arcgis/rest/services/"
        "Avalanche_Observations/FeatureServer/0"
    )

    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{layer_url}/query"
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer arcgis-access"
        body = request.content.decode("utf-8")
        assert "where=zone%3D%27Cardiff%27" in body
        assert "outFields=OBJECTID%2Czone" in body
        assert "resultRecordCount=25" in body
        return httpx.Response(
            200,
            json={
                "geometryType": "esriGeometryPoint",
                "features": [
                    {
                        "attributes": {
                            "OBJECTID": 1,
                            "zone": "Cardiff",
                        },
                        "geometry": {"x": -111.65, "y": 40.59},
                    }
                ],
                "exceededTransferLimit": False,
            },
        )

    result = await query_arcgis_features(
        {"access_token": "arcgis-access"},
        layer_url=layer_url,
        where="zone='Cardiff'",
        out_fields=["OBJECTID", "zone"],
        result_record_count=25,
        transport=httpx.MockTransport(responder),
    )
    assert result.metadata["feature_count"] == 1
    assert result.metadata["geometry_type"] == "esriGeometryPoint"


@pytest.mark.asyncio
async def test_arcgis_feature_query_rejects_non_arcgis_destination() -> None:
    with pytest.raises(InvalidConfiguration, match="ArcGIS Online"):
        await query_arcgis_features(
            {"access_token": "arcgis-access"},
            layer_url="https://example.com/arcgis/rest/services/Test/FeatureServer/0",
        )


@pytest.mark.asyncio
async def test_microsoft_file_export_uses_graph_and_bearer_token() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.host == "graph.microsoft.com"
        assert request.url.path.endswith("/me/drive/root:/Reports/shift-report.txt:/content")
        assert request.headers["Authorization"] == "Bearer ms-access"
        assert request.content == b"Shift report"
        return httpx.Response(
            201,
            json={
                "id": "drive-item-1",
                "name": "shift-report.txt",
                "size": 12,
                "webUrl": "https://example.sharepoint.com/file",
            },
        )

    result = await create_microsoft_drive_file(
        {"access_token": "ms-access"},
        name="shift-report.txt",
        content="Shift report",
        mime_type="text/plain",
        folder_path="Reports",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "drive-item-1"


@pytest.mark.asyncio
async def test_microsoft_sharepoint_export_targets_approved_site_drive() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.host == "graph.microsoft.com"
        assert request.url.path == (
            "/v1.0/sites/contoso.sharepoint.com,site-collection,site-id/"
            "drive/root:/Operations/handoff.md:/content"
        )
        assert request.headers["Authorization"] == "Bearer ms-access"
        return httpx.Response(
            201,
            json={
                "id": "sharepoint-item-1",
                "name": "handoff.md",
                "size": 12,
                "webUrl": "https://contoso.sharepoint.com/file",
            },
        )

    result = await create_microsoft_drive_file(
        {"access_token": "ms-access"},
        name="handoff.md",
        content="Shift report",
        mime_type="text/markdown",
        folder_path="Operations",
        site_id="contoso.sharepoint.com,site-collection,site-id",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "sharepoint-item-1"
    assert result.metadata["target"] == "sharepoint_site"


@pytest.mark.asyncio
async def test_google_calendar_event_uses_configured_calendar() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == (
            "/calendar/v3/calendars/ops%40group.calendar.google.com/events"
        )
        payload = json.loads(request.content)
        assert payload["summary"] == "Shift briefing"
        assert payload["start"]["dateTime"] == "2026-09-22T08:00:00-06:00"
        return httpx.Response(
            201,
            json={
                "id": "google-event-1",
                "htmlLink": "https://calendar.google.com/event?eid=1",
                "status": "confirmed",
            },
        )

    result = await create_google_calendar_event(
        {"access_token": "google-calendar-access"},
        calendar_id="ops@group.calendar.google.com",
        title="Shift briefing",
        start="2026-09-22T08:00:00-06:00",
        end="2026-09-22T09:00:00-06:00",
        description="Morning operational briefing",
        location="Operations room",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "google-event-1"
    assert result.metadata["calendar_id"] == "ops@group.calendar.google.com"


@pytest.mark.asyncio
async def test_microsoft_calendar_event_normalizes_to_utc() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1.0/me/calendars/shared-calendar/events"
        payload = json.loads(request.content)
        assert payload["subject"] == "Shift briefing"
        assert payload["start"] == {
            "dateTime": "2026-09-22T14:00:00",
            "timeZone": "UTC",
        }
        assert payload["end"] == {
            "dateTime": "2026-09-22T15:00:00",
            "timeZone": "UTC",
        }
        return httpx.Response(
            201,
            json={
                "id": "ms-event-1",
                "webLink": "https://outlook.office.com/calendar/item/1",
                "isCancelled": False,
            },
        )

    result = await create_microsoft_calendar_event(
        {"access_token": "ms-calendar-access"},
        calendar_id="shared-calendar",
        title="Shift briefing",
        start="2026-09-22T08:00:00-06:00",
        end="2026-09-22T09:00:00-06:00",
        transport=httpx.MockTransport(responder),
    )
    assert result.external_id == "ms-event-1"
    assert result.metadata["calendar_id"] == "shared-calendar"


@pytest.mark.asyncio
async def test_calendar_events_require_offset_and_positive_duration() -> None:
    with pytest.raises(InvalidConfiguration, match="UTC offset"):
        await create_google_calendar_event(
            {"access_token": "calendar-access"},
            calendar_id=None,
            title="Bad event",
            start="2026-09-22T08:00:00",
            end="2026-09-22T09:00:00",
        )
    with pytest.raises(InvalidConfiguration, match="after start"):
        await create_microsoft_calendar_event(
            {"access_token": "calendar-access"},
            calendar_id=None,
            title="Bad event",
            start="2026-09-22T10:00:00-06:00",
            end="2026-09-22T09:00:00-06:00",
        )


@pytest.mark.asyncio
async def test_caltopo_map_query_signs_request_and_never_sends_secret() -> None:
    secret = base64.b64encode(b"cal-secret").decode("ascii")

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "caltopo.com"
        assert request.url.path == "/api/v1/map/ABC123/since/0"
        assert request.url.params["id"] == "credential-id"
        assert "signature" in request.url.params
        assert "cal-secret" not in str(request.url)
        return httpx.Response(
            200,
            json={"result": {"features": [], "timestamp": 123}},
        )

    result = await query_caltopo_map(
        {
            "credential_id": "credential-id",
            "credential_secret": secret,
        },
        map_id="ABC123",
        transport=httpx.MockTransport(responder),
    )
    assert result.metadata["feature_count"] == 0


@pytest.mark.asyncio
async def test_snowflake_query_allows_only_single_select() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "org-account.snowflakecomputing.com"
        assert request.headers["Authorization"] == "Bearer snow-pat"
        assert request.headers["X-Snowflake-Authorization-Token-Type"] == (
            "PROGRAMMATIC_ACCESS_TOKEN"
        )
        assert json.loads(request.content)["statement"] == "SELECT CURRENT_TIMESTAMP()"
        return httpx.Response(
            200,
            json={"statementHandle": "handle-1", "data": [["2026-09-20"]]},
        )

    result = await query_snowflake(
        {"programmatic_access_token": "snow-pat"},
        account_host="org-account.snowflakecomputing.com",
        statement="SELECT CURRENT_TIMESTAMP()",
        transport=httpx.MockTransport(responder),
    )
    assert result.metadata["row_count"] == 1

    with pytest.raises(InvalidConfiguration, match="read-only SELECT"):
        await query_snowflake(
            {"programmatic_access_token": "snow-pat"},
            account_host="org-account.snowflakecomputing.com",
            statement="DELETE FROM observations",
        )


@pytest.mark.asyncio
async def test_mapbox_style_read_uses_fixed_api_host() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.mapbox.com"
        assert request.url.path == "/styles/v1/terrasatch/field-style"
        assert request.url.params["access_token"] == "pk.test"
        return httpx.Response(
            200,
            json={"version": 8, "name": "Field", "sources": {}, "layers": []},
        )

    result = await read_mapbox_style(
        access_token="pk.test",
        username="terrasatch",
        style_id="field-style",
        transport=httpx.MockTransport(responder),
    )
    assert result.metadata["name"] == "Field"


@pytest.mark.asyncio
async def test_stac_item_search_uses_allowlisted_core_parameters() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://stac.example.com/api/search?")
        assert dict(request.url.params) == {
            "collections": "sentinel-2",
            "limit": "20",
            "bbox": "-112.0,40.0,-111.0,41.0",
            "datetime": "2026-09-20/2026-09-21",
        }
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "numberMatched": 2,
                "numberReturned": 2,
                "features": [
                    {
                        "type": "Feature",
                        "stac_version": "1.0.0",
                        "id": "scene-a",
                        "geometry": None,
                        "properties": {"datetime": "2026-09-20T12:00:00Z"},
                        "assets": {},
                    },
                    {
                        "type": "Feature",
                        "stac_version": "1.0.0",
                        "id": "scene-b",
                        "geometry": None,
                        "properties": {"datetime": "2026-09-20T13:00:00Z"},
                        "assets": {},
                    },
                ],
            },
        )

    result = await query_stac_items(
        base_url="https://stac.example.com/api",
        collection_id="sentinel-2",
        limit=20,
        bbox=[-112, 40, -111, 41],
        datetime_value="2026-09-20/2026-09-21",
        transport=httpx.MockTransport(responder),
    )
    assert result.metadata["collection_id"] == "sentinel-2"
    assert result.metadata["item_count"] == 2
    assert result.metadata["number_matched"] == 2


def test_stac_api_rejects_unsafe_base_url() -> None:
    with pytest.raises(InvalidConfiguration, match="without credentials"):
        validate_stac_api_base_url("https://user:pass@stac.example.com/api")


@pytest.mark.asyncio
async def test_stac_api_rejects_private_dns_resolution(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [(2, 1, 6, "", ("172.16.0.4", 443))]

    monkeypatch.setattr(
        "terrasatch.integrations.operations.socket.getaddrinfo",
        fake_getaddrinfo,
    )
    with pytest.raises(InvalidConfiguration, match="non-public address"):
        await validate_public_stac_destination("https://stac.example.com/api")


@pytest.mark.asyncio
async def test_stac_api_rejects_non_stac_items() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "missing-version",
                        "geometry": None,
                        "properties": {},
                    }
                ],
            },
        )
    )
    with pytest.raises(ProviderUnavailable, match="invalid STAC Item"):
        await query_stac_items(
            base_url="https://stac.example.com/api",
            collection_id="sentinel-2",
            limit=10,
            transport=transport,
        )


@pytest.mark.asyncio
async def test_public_arcgis_enterprise_query_has_no_auth_and_is_bounded() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == (
            "https://gis.example.gov/server/rest/services/"
            "Avalanche/FeatureServer/0/query"
        )
        assert "Authorization" not in request.headers
        form = dict(request.url.params)
        assert form == {}
        body = request.content.decode()
        assert "where=STATUS%3D%27OPEN%27" in body
        assert "outFields=NAME%2CSTATUS" in body
        assert "resultRecordCount=25" in body
        return httpx.Response(
            200,
            json={
                "objectIdFieldName": "OBJECTID",
                "geometryType": "esriGeometryPoint",
                "features": [
                    {
                        "attributes": {
                            "OBJECTID": 1,
                            "NAME": "Observation",
                            "STATUS": "OPEN",
                        },
                        "geometry": {"x": -111.8, "y": 40.6},
                    }
                ],
            },
        )

    result = await query_public_arcgis_features(
        layer_url=(
            "https://gis.example.gov/server/rest/services/"
            "Avalanche/FeatureServer/0"
        ),
        where="STATUS='OPEN'",
        out_fields=["NAME", "STATUS"],
        return_geometry=True,
        result_record_count=25,
        result_offset=0,
        transport=httpx.MockTransport(responder),
    )
    assert result.metadata["feature_count"] == 1
    assert result.metadata["source_host"] == "gis.example.gov"


def test_public_arcgis_enterprise_rejects_unsafe_layer_urls() -> None:
    for url in (
        "http://gis.example.gov/server/rest/services/A/FeatureServer/0",
        "https://127.0.0.1/server/rest/services/A/FeatureServer/0",
        "https://user:pass@gis.example.gov/server/rest/services/A/FeatureServer/0",
        "https://gis.example.gov/server/rest/services/A/MapServer/0",
    ):
        with pytest.raises(InvalidConfiguration):
            validate_public_arcgis_feature_layer_url(url)


@pytest.mark.asyncio
async def test_public_arcgis_enterprise_rejects_private_dns(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [(2, 1, 6, "", ("10.1.2.3", 443))]

    monkeypatch.setattr(
        "terrasatch.integrations.operations.socket.getaddrinfo",
        fake_getaddrinfo,
    )
    with pytest.raises(InvalidConfiguration, match="non-public address"):
        await validate_public_arcgis_feature_layer_destination(
            "https://gis.example.gov/server/rest/services/A/FeatureServer/0"
        )


@pytest.mark.asyncio
async def test_nws_forecast_discovers_grid_and_uses_required_user_agent() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == "TerraSatch/0.3 (+https://terrasatch.com)"
        if request.url.path == "/points/40.6000,-111.7000":
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "forecast": (
                            "https://api.weather.gov/gridpoints/SLC/100,200/forecast"
                        ),
                        "gridId": "SLC",
                        "gridX": 100,
                        "gridY": 200,
                    }
                },
            )
        assert request.url.path == "/gridpoints/SLC/100,200/forecast"
        return httpx.Response(
            200,
            json={
                "properties": {
                    "updated": "2026-09-21T12:00:00+00:00",
                    "generatedAt": "2026-09-21T12:00:00+00:00",
                    "units": "us",
                    "periods": [
                        {"number": 1, "name": "Today", "temperature": 60},
                        {"number": 2, "name": "Tonight", "temperature": 38},
                        {"number": 3, "name": "Monday", "temperature": 58},
                    ],
                }
            },
        )

    result = await query_nws_forecast(
        latitude=40.6,
        longitude=-111.7,
        max_periods=2,
        transport=httpx.MockTransport(responder),
    )
    assert len(result.data["periods"]) == 2
    assert result.metadata == {
        "source_host": "api.weather.gov",
        "latitude": 40.6,
        "longitude": -111.7,
        "office": "SLC",
        "grid_x": 100,
        "grid_y": 200,
        "period_count": 2,
        "source_period_count": 3,
        "truncated": True,
    }


@pytest.mark.asyncio
async def test_nws_rejects_forecast_link_to_other_host() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "properties": {
                    "forecast": "https://example.com/gridpoints/SLC/1,2/forecast"
                }
            },
        )

    with pytest.raises(ProviderUnavailable, match="invalid forecast URL"):
        await query_nws_forecast(
            latitude=40.6,
            longitude=-111.7,
            max_periods=2,
            transport=httpx.MockTransport(responder),
        )


@pytest.mark.asyncio
async def test_nws_rejects_invalid_coordinates_and_forecast_ports() -> None:
    with pytest.raises(InvalidConfiguration, match="coordinates"):
        await query_nws_forecast(
            latitude=100,
            longitude=-111.7,
            max_periods=2,
            transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        )
    with pytest.raises(ProviderUnavailable, match="invalid forecast URL"):
        validate_nws_forecast_url(
            "https://api.weather.gov:bad/gridpoints/SLC/1,2/forecast"
        )


@pytest.mark.asyncio
async def test_nws_probe_uses_fixed_service_root() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://api.weather.gov/points/39.7456,-97.0892"
        )
        assert request.headers["User-Agent"].startswith("TerraSatch/")
        return httpx.Response(200, json={"status": "ok"})

    result = await probe_nws_api(transport=httpx.MockTransport(responder))
    assert result.external_id == "api.weather.gov"
