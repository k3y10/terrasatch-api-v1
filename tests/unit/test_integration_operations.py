"""Provider output primitive tests with no live external traffic."""

import json

import httpx
import pytest

from terrasatch.errors import InvalidConfiguration
from terrasatch.integrations.operations import (
    create_google_drive_file,
    query_arcgis_features,
    send_slack_message,
)


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
