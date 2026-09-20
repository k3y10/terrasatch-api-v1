"""Provider-specific output primitives used by approved TerraSatch workflows."""

from __future__ import annotations

import base64
from binascii import Error as BinasciiError
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

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



_MICROSOFT_GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
_CALTOPO_ROOT = "https://caltopo.com"
_MAPBOX_STYLES_ROOT = "https://api.mapbox.com/styles/v1"


async def create_microsoft_drive_file(
    credentials: dict[str, object],
    *,
    name: str,
    content: str,
    mime_type: str,
    folder_path: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    access_token = credentials.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ProviderUnavailable("Microsoft access token is unavailable")

    clean_name = " ".join(name.split())
    if not clean_name or len(clean_name) > 255 or "/" in clean_name or "\\" in clean_name:
        raise InvalidConfiguration("Microsoft file name is invalid")
    media = content.encode("utf-8")
    if len(media) > 5_000_000:
        raise InvalidConfiguration("Microsoft file export is limited to 5 MB")

    path_parts: list[str] = []
    if folder_path:
        path_parts.extend(
            part.strip()
            for part in folder_path.replace("\\", "/").split("/")
            if part.strip()
        )
    if any(part in {".", ".."} for part in path_parts):
        raise InvalidConfiguration("Microsoft folder path is invalid")
    path_parts.append(clean_name)
    encoded_path = "/".join(quote(part, safe="") for part in path_parts)
    url = f"{_MICROSOFT_GRAPH_ROOT}/me/drive/root:/{encoded_path}:/content"
    response = await _request(
        transport,
        "PUT",
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": mime_type,
        },
        content=media,
    )
    if response.status_code not in {200, 201}:
        raise ProviderUnavailable(
            f"Microsoft file export failed with HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable("Microsoft Graph returned an invalid file response") from error
    if not isinstance(payload, dict) or not payload.get("id"):
        raise ProviderUnavailable("Microsoft Graph did not return a file ID")
    safe = {
        "id": str(payload["id"]),
        "name": payload.get("name"),
        "size": payload.get("size"),
        "web_url": payload.get("webUrl"),
    }
    return ProviderOperationResult(
        external_id=str(payload["id"]),
        metadata={key: value for key, value in safe.items() if value is not None},
    )


def _caltopo_signature(
    method: str,
    endpoint: str,
    expires: int,
    payload_string: str,
    credential_secret: str,
) -> str:
    try:
        secret = base64.b64decode(credential_secret, validate=True)
    except (BinasciiError, ValueError, TypeError) as error:
        raise InvalidConfiguration("CalTopo credential secret is not valid base64") from error
    message = f"{method.upper()} {endpoint}\n{expires}\n{payload_string}"
    digest = hmac.new(secret, message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


async def _caltopo_get(
    credentials: dict[str, object],
    endpoint: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    credential_id = credentials.get("credential_id")
    credential_secret = credentials.get("credential_secret")
    if not isinstance(credential_id, str) or not credential_id.strip():
        raise ProviderUnavailable("CalTopo credential ID is unavailable")
    if not isinstance(credential_secret, str) or not credential_secret.strip():
        raise ProviderUnavailable("CalTopo credential secret is unavailable")
    expires = int(time.time() * 1000) + 120_000
    signature = _caltopo_signature(
        "GET",
        endpoint,
        expires,
        "",
        credential_secret,
    )
    response = await _request(
        transport,
        "GET",
        f"{_CALTOPO_ROOT}{endpoint}",
        params={
            "id": credential_id,
            "expires": str(expires),
            "signature": signature,
        },
    )
    if response.status_code >= 400:
        raise ProviderUnavailable(
            f"CalTopo request failed with HTTP {response.status_code}"
        )
    if len(response.content) > 2_000_000:
        raise ProviderUnavailable("CalTopo response exceeded the 2 MB safety limit")
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable("CalTopo returned an invalid response") from error
    if not isinstance(payload, dict):
        raise ProviderUnavailable("CalTopo returned an invalid response")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ProviderUnavailable("CalTopo returned no result")
    return result


async def query_caltopo_team(
    credentials: dict[str, object],
    *,
    team_id: str,
    since: int = 0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    clean_team = team_id.strip()
    if len(clean_team) != 6 or not clean_team.isalnum():
        raise InvalidConfiguration("CalTopo team ID is invalid")
    if not 0 <= since <= 9_999_999_999_999:
        raise InvalidConfiguration("CalTopo since timestamp is invalid")
    data = await _caltopo_get(
        credentials,
        f"/api/v1/acct/{clean_team}/since/{since}",
        transport=transport,
    )
    features = data.get("features")
    feature_count = len(features) if isinstance(features, list) else 0
    return ProviderQueryResult(
        data=data,
        metadata={
            "team_id": clean_team,
            "feature_count": feature_count,
            "timestamp": data.get("timestamp"),
        },
    )


async def query_caltopo_map(
    credentials: dict[str, object],
    *,
    map_id: str,
    since: int = 0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    clean_map = map_id.strip()
    if not 4 <= len(clean_map) <= 32 or not clean_map.isalnum():
        raise InvalidConfiguration("CalTopo map ID is invalid")
    if not 0 <= since <= 9_999_999_999_999:
        raise InvalidConfiguration("CalTopo since timestamp is invalid")
    data = await _caltopo_get(
        credentials,
        f"/api/v1/map/{clean_map}/since/{since}",
        transport=transport,
    )
    features = data.get("features")
    feature_count = len(features) if isinstance(features, list) else 0
    return ProviderQueryResult(
        data=data,
        metadata={
            "map_id": clean_map,
            "feature_count": feature_count,
            "timestamp": data.get("timestamp"),
        },
    )


async def query_snowflake(
    credentials: dict[str, object],
    *,
    account_host: str,
    statement: str,
    warehouse: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    role: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    token = credentials.get("programmatic_access_token")
    if not isinstance(token, str) or not token:
        raise ProviderUnavailable("Snowflake programmatic access token is unavailable")
    host = account_host.strip().casefold()
    if (
        not host.endswith(".snowflakecomputing.com")
        or "://" in host
        or "/" in host
    ):
        raise InvalidConfiguration("Snowflake account host is invalid")

    normalized = " ".join(statement.split()).strip()
    upper = normalized.upper()
    if (
        not upper.startswith("SELECT ")
        or ";" in normalized
        or "--" in normalized
        or "/*" in normalized
        or len(normalized) > 5000
    ):
        raise InvalidConfiguration("Snowflake data.query accepts one read-only SELECT statement")

    body: dict[str, object] = {"statement": normalized, "timeout": 30}
    for key, value in {
        "warehouse": warehouse,
        "database": database,
        "schema": schema,
        "role": role,
    }.items():
        if value:
            body[key] = value

    response = await _request(
        transport,
        "POST",
        f"https://{host}/api/v2/statements",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json=body,
    )
    if response.status_code >= 400:
        raise ProviderUnavailable(
            f"Snowflake query failed with HTTP {response.status_code}"
        )
    if len(response.content) > 2_000_000:
        raise ProviderUnavailable("Snowflake query response exceeded the 2 MB safety limit")
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable("Snowflake returned an invalid response") from error
    if not isinstance(payload, dict):
        raise ProviderUnavailable("Snowflake returned an invalid response")
    if payload.get("code") and not payload.get("data"):
        raise ProviderUnavailable(
            f"Snowflake query failed ({str(payload.get('code'))[:80]})"
        )
    data_rows = payload.get("data")
    row_count = len(data_rows) if isinstance(data_rows, list) else 0
    return ProviderQueryResult(
        data=payload,
        metadata={
            "row_count": row_count,
            "statement_handle": payload.get("statementHandle"),
        },
    )


async def read_mapbox_style(
    *,
    access_token: str,
    username: str,
    style_id: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    clean_username = username.strip()
    clean_style = style_id.strip()
    if (
        not clean_username
        or not clean_style
        or len(clean_username) > 255
        or len(clean_style) > 255
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", clean_username)
        or not re.fullmatch(r"[A-Za-z0-9_-]+", clean_style)
    ):
        raise InvalidConfiguration("Mapbox username or style_id is invalid")
    response = await _request(
        transport,
        "GET",
        f"{_MAPBOX_STYLES_ROOT}/{clean_username}/{clean_style}",
        params={"access_token": access_token},
    )
    if response.status_code >= 400:
        raise ProviderUnavailable(
            f"Mapbox style request failed with HTTP {response.status_code}"
        )
    if len(response.content) > 2_000_000:
        raise ProviderUnavailable("Mapbox style response exceeded the 2 MB safety limit")
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable("Mapbox returned an invalid style response") from error
    if not isinstance(payload, dict):
        raise ProviderUnavailable("Mapbox returned an invalid style response")
    return ProviderQueryResult(
        data=payload,
        metadata={
            "username": clean_username,
            "style_id": clean_style,
            "name": payload.get("name"),
        },
    )
