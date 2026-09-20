"""Provider-specific output primitives used by approved TerraSatch workflows."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from terrasatch.errors import InvalidConfiguration, ProviderUnavailable

_SLACK_WEBHOOK_HOST = "hooks.slack.com"
_DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
_ALLOWED_DRIVE_MIME_TYPES = {
    "application/json",
    "text/csv",
    "text/markdown",
    "text/plain",
}


@dataclass(frozen=True, slots=True)
class ProviderOperationResult:
    external_id: str | None
    metadata: dict[str, object]


async def _request(
    transport: httpx.AsyncBaseTransport | None,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=False,
            transport=transport,
        ) as client:
            return await client.request(method, url, **kwargs)
    except httpx.HTTPError as error:
        raise ProviderUnavailable("Provider delivery request failed") from error


def _slack_webhook(credentials: dict[str, object]) -> tuple[str, dict[str, object]]:
    incoming = credentials.get("incoming_webhook")
    if not isinstance(incoming, dict):
        raise ProviderUnavailable("Slack incoming webhook is unavailable; reconnect Slack")
    url = incoming.get("url")
    if not isinstance(url, str) or not url:
        raise ProviderUnavailable("Slack incoming webhook is unavailable; reconnect Slack")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != _SLACK_WEBHOOK_HOST:
        raise InvalidConfiguration("Stored Slack webhook destination is invalid")
    return url, incoming


async def send_slack_message(
    credentials: dict[str, object],
    *,
    text: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    normalized = text.strip()
    if not normalized:
        raise InvalidConfiguration("Slack message cannot be empty")
    if len(normalized) > 4000:
        raise InvalidConfiguration("Slack message is limited to 4000 characters")

    url, incoming = _slack_webhook(credentials)
    response = await _request(
        transport,
        "POST",
        url,
        json={"text": normalized},
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    if response.status_code != 200 or response.text.strip() != "ok":
        raise ProviderUnavailable(
            f"Slack webhook delivery failed with HTTP {response.status_code}"
        )
    metadata = {
        "channel": incoming.get("channel"),
        "channel_id": incoming.get("channel_id"),
    }
    return ProviderOperationResult(
        external_id=str(incoming.get("channel_id") or "") or None,
        metadata={key: value for key, value in metadata.items() if value},
    )


async def create_google_drive_file(
    credentials: dict[str, object],
    *,
    name: str,
    content: str,
    mime_type: str,
    folder_id: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    access_token = credentials.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ProviderUnavailable("Google Drive access token is unavailable")

    clean_name = " ".join(name.split())
    if not clean_name or len(clean_name) > 255:
        raise InvalidConfiguration("Drive export name must be between 1 and 255 characters")
    if mime_type not in _ALLOWED_DRIVE_MIME_TYPES:
        raise InvalidConfiguration("Drive export MIME type is not allowed")

    media = content.encode("utf-8")
    if len(media) > 5_000_000:
        raise InvalidConfiguration("Drive export is limited to 5 MB")

    metadata: dict[str, object] = {"name": clean_name}
    if folder_id is not None:
        clean_folder = folder_id.strip()
        if not clean_folder or len(clean_folder) > 512:
            raise InvalidConfiguration("Google Drive folder ID is invalid")
        metadata["parents"] = [clean_folder]

    boundary = f"terrasatch_{secrets.token_hex(16)}"
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata, separators=(',', ':'))}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + media + f"\r\n--{boundary}--\r\n".encode("ascii")

    response = await _request(
        transport,
        "POST",
        _DRIVE_UPLOAD_URL,
        params={
            "uploadType": "multipart",
            "fields": "id,name,mimeType,webViewLink",
        },
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        content=body,
    )
    if response.status_code >= 400:
        raise ProviderUnavailable(
            f"Google Drive export failed with HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable("Google Drive returned an invalid upload response") from error
    if not isinstance(payload, dict) or not payload.get("id"):
        raise ProviderUnavailable("Google Drive did not return a file ID")

    external_id = str(payload["id"])
    safe = {
        "id": external_id,
        "name": payload.get("name"),
        "mime_type": payload.get("mimeType"),
        "web_view_link": payload.get("webViewLink"),
    }
    return ProviderOperationResult(
        external_id=external_id,
        metadata={key: value for key, value in safe.items() if value is not None},
    )
