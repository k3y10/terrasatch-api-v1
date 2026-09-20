"""Provider output primitive tests with no live external traffic."""

import json

import httpx
import pytest

from terrasatch.errors import InvalidConfiguration
from terrasatch.integrations.operations import (
    create_google_drive_file,
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
