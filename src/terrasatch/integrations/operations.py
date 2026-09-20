"""Provider-specific output primitives used by approved TerraSatch workflows."""

from __future__ import annotations

import json
import re
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


@dataclass(frozen=True, slots=True)
class ProviderQueryResult:
    data: dict[str, object]
    metadata: dict[str, object]


_ARCGIS_LAYER_PATH = re.compile(r"/FeatureServer/\d+/?$", re.I)
_ARCGIS_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_arcgis_feature_layer_url(value: str) -> str:
    """Validate an ArcGIS Online feature-layer URL and return its canonical form."""

    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").casefold()
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not hostname.endswith(".arcgis.com")
        or not _ARCGIS_LAYER_PATH.search(parsed.path)
    ):
        raise InvalidConfiguration(
            "ArcGIS feature layer must be an HTTPS ArcGIS Online FeatureServer layer URL"
        )
    return normalized


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

    metadata: dict[str, object] = {
        "name": clean_name,
        "mimeType": mime_type,
    }
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
            "supportsAllDrives": "true",
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



async def query_arcgis_features(
    credentials: dict[str, object],
    *,
    layer_url: str,
    where: str = "1=1",
    out_fields: list[str] | None = None,
    return_geometry: bool = True,
    result_record_count: int = 100,
    result_offset: int = 0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    """Query one allowlisted ArcGIS Online feature layer with a bearer token."""

    access_token = credentials.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ProviderUnavailable("ArcGIS access token is unavailable")

    normalized_layer = validate_arcgis_feature_layer_url(layer_url)
    normalized_where = " ".join(where.split()).strip()
    if not normalized_where or len(normalized_where) > 2000:
        raise InvalidConfiguration("ArcGIS where clause must be between 1 and 2000 characters")

    fields = out_fields or ["*"]
    if not fields or len(fields) > 50:
        raise InvalidConfiguration("ArcGIS out_fields must contain between 1 and 50 fields")
    normalized_fields: list[str] = []
    for field in fields:
        candidate = field.strip()
        if candidate != "*" and not _ARCGIS_FIELD.fullmatch(candidate):
            raise InvalidConfiguration("ArcGIS out_fields contains an invalid field name")
        normalized_fields.append(candidate)

    if not 1 <= result_record_count <= 200:
        raise InvalidConfiguration("ArcGIS queries are limited to 200 features per request")
    if not 0 <= result_offset <= 1_000_000:
        raise InvalidConfiguration("ArcGIS result offset is outside the allowed range")

    response = await _request(
        transport,
        "POST",
        f"{normalized_layer}/query",
        data={
            "f": "json",
            "where": normalized_where,
            "outFields": ",".join(normalized_fields),
            "returnGeometry": "true" if return_geometry else "false",
            "resultRecordCount": str(result_record_count),
            "resultOffset": str(result_offset),
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code >= 400:
        raise ProviderUnavailable(
            f"ArcGIS feature query failed with HTTP {response.status_code}"
        )
    if len(response.content) > 2_000_000:
        raise ProviderUnavailable("ArcGIS feature query response exceeded the 2 MB safety limit")
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable("ArcGIS returned an invalid feature response") from error
    if not isinstance(payload, dict):
        raise ProviderUnavailable("ArcGIS returned an invalid feature response")
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        code = error_payload.get("code")
        message = error_payload.get("message") or "query_failed"
        raise ProviderUnavailable(f"ArcGIS query failed ({code}: {message})")

    features = payload.get("features")
    if features is not None and not isinstance(features, list):
        raise ProviderUnavailable("ArcGIS returned an invalid feature collection")
    feature_count = len(features or [])
    metadata: dict[str, object] = {
        "feature_count": feature_count,
        "layer_url": normalized_layer,
        "return_geometry": return_geometry,
    }
    if payload.get("geometryType"):
        metadata["geometry_type"] = payload["geometryType"]
    if payload.get("exceededTransferLimit") is not None:
        metadata["exceeded_transfer_limit"] = bool(payload["exceededTransferLimit"])
    return ProviderQueryResult(data=payload, metadata=metadata)
