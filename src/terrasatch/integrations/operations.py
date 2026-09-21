"""Provider-specific output primitives used by approved TerraSatch workflows."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import socket
import time
from binascii import Error as BinasciiError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx

from terrasatch.errors import InvalidConfiguration, ProviderUnavailable

_SLACK_WEBHOOK_HOST = "hooks.slack.com"
_TEAMS_WEBHOOK_HOST_SUFFIXES = (".logic.azure.com", ".api.powerplatform.com")
_R2_ENDPOINT_SUFFIX = ".r2.cloudflarestorage.com"
_S3_BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_NWS_ROOT = "https://api.weather.gov"
_NWS_USER_AGENT = "TerraSatch/0.3 (+https://terrasatch.com)"
_NWS_FORECAST_PATH = re.compile(
    r"^/gridpoints/[A-Z]{3}/[0-9]+,[0-9]+/forecast/?$"
)
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
_OGC_COLLECTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$")
_STAC_COLLECTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$")
_OGC_DATETIME = re.compile(
    r"^(?:\.\.|[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9:.+-]+Z?)?)"
    r"(?:/(?:\.\.|[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9:.+-]+Z?)?))?$"
)


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


def validate_public_arcgis_feature_layer_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as error:
        raise InvalidConfiguration(
            "Public ArcGIS Enterprise layer URL has an invalid port"
        ) from error
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
        or not _ARCGIS_LAYER_PATH.search(parsed.path)
    ):
        raise InvalidConfiguration(
            "Public ArcGIS Enterprise layer must be an HTTPS FeatureServer layer URL"
        )
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise InvalidConfiguration(
            "Public ArcGIS Enterprise layer must use a DNS hostname"
        )
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise InvalidConfiguration(
            "Public ArcGIS Enterprise layer destination is not allowed"
        )
    return normalized


async def validate_public_arcgis_feature_layer_destination(value: str) -> str:
    normalized = validate_public_arcgis_feature_layer_url(value)
    return await _validate_public_hostname(
        normalized,
        label="Public ArcGIS Enterprise layer",
    )


def _validate_https_webhook_url(
    value: str,
    *,
    label: str,
    allowed_host_suffixes: tuple[str, ...] | None = None,
) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as error:
        raise InvalidConfiguration(f"{label} webhook URL has an invalid port") from error

    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise InvalidConfiguration(
            f"{label} webhook must be an HTTPS URL without embedded credentials or fragments"
        )

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise InvalidConfiguration(f"{label} webhook must use a DNS hostname")

    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise InvalidConfiguration(f"{label} webhook destination is not allowed")

    if allowed_host_suffixes is not None and not any(
        hostname.endswith(suffix) for suffix in allowed_host_suffixes
    ):
        raise InvalidConfiguration(f"{label} webhook destination is not allowed")

    return normalized


async def _validate_public_hostname(normalized: str, *, label: str) -> str:
    hostname = urlsplit(normalized).hostname
    assert hostname is not None
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            443,
            0,
            socket.SOCK_STREAM,
        )
    except OSError as error:
        raise ProviderUnavailable(
            f"{label} destination could not be resolved"
        ) from error

    addresses = {item[4][0].split("%", 1)[0] for item in infos if item[4]}
    if not addresses:
        raise ProviderUnavailable(f"{label} destination could not be resolved")

    for address in addresses:
        try:
            resolved = ipaddress.ip_address(address)
        except ValueError as error:
            raise ProviderUnavailable(
                f"{label} destination returned an invalid address"
            ) from error
        if not resolved.is_global:
            raise InvalidConfiguration(
                f"{label} destination resolves to a non-public address"
            )
    return normalized


async def validate_public_webhook_destination(
    value: str,
    *,
    label: str,
    allowed_host_suffixes: tuple[str, ...] | None = None,
) -> str:
    normalized = _validate_https_webhook_url(
        value,
        label=label,
        allowed_host_suffixes=allowed_host_suffixes,
    )
    return await _validate_public_hostname(normalized, label=f"{label} webhook")


def validate_geojson_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as error:
        raise InvalidConfiguration("GeoJSON endpoint has an invalid port") from error
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise InvalidConfiguration(
            "GeoJSON endpoint must be an HTTPS URL without credentials, query, or fragment"
        )
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise InvalidConfiguration("GeoJSON endpoint must use a DNS hostname")
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise InvalidConfiguration("GeoJSON endpoint destination is not allowed")
    return normalized


async def validate_public_geojson_destination(value: str) -> str:
    normalized = validate_geojson_url(value)
    return await _validate_public_hostname(normalized, label="GeoJSON endpoint")


def validate_ogc_api_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as error:
        raise InvalidConfiguration("OGC API base URL has an invalid port") from error
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise InvalidConfiguration(
            "OGC API base URL must be HTTPS without credentials, query, or fragment"
        )
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise InvalidConfiguration("OGC API base URL must use a DNS hostname")
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise InvalidConfiguration("OGC API destination is not allowed")
    return normalized


async def validate_public_ogc_destination(value: str) -> str:
    normalized = validate_ogc_api_base_url(value)
    return await _validate_public_hostname(normalized, label="OGC API")


def validate_stac_api_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as error:
        raise InvalidConfiguration("STAC API base URL has an invalid port") from error
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise InvalidConfiguration(
            "STAC API base URL must be HTTPS without credentials, query, or fragment"
        )
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise InvalidConfiguration("STAC API base URL must use a DNS hostname")
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        raise InvalidConfiguration("STAC API destination is not allowed")
    return normalized


async def validate_public_stac_destination(value: str) -> str:
    normalized = validate_stac_api_base_url(value)
    return await _validate_public_hostname(normalized, label="STAC API")


def validate_stac_collection_id(value: str) -> str:
    normalized = value.strip()
    if not _STAC_COLLECTION_ID.fullmatch(normalized):
        raise InvalidConfiguration("STAC collection ID is invalid")
    return normalized


def validate_ogc_collection_id(value: str) -> str:
    normalized = value.strip()
    if not _OGC_COLLECTION_ID.fullmatch(normalized):
        raise InvalidConfiguration("OGC collection ID is invalid")
    return normalized


def validate_generic_webhook_url(value: str) -> str:
    return _validate_https_webhook_url(value, label="Generic")


def validate_teams_workflow_url(value: str) -> str:
    normalized = _validate_https_webhook_url(
        value,
        label="Microsoft Teams",
        allowed_host_suffixes=_TEAMS_WEBHOOK_HOST_SUFFIXES,
    )
    parsed = urlsplit(normalized)
    if "/workflows/" not in parsed.path or "/triggers/" not in parsed.path:
        raise InvalidConfiguration("Microsoft Teams Workflows webhook path is invalid")
    return normalized


def validate_r2_endpoint_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as error:
        raise InvalidConfiguration("Cloudflare R2 endpoint has an invalid port") from error
    if (
        parsed.scheme != "https"
        or not hostname.endswith(_R2_ENDPOINT_SUFFIX)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or port not in {None, 443}
    ):
        raise InvalidConfiguration(
            "Cloudflare R2 endpoint must be the HTTPS S3 API account endpoint"
        )
    return f"https://{hostname}"


def validate_s3_bucket_name(value: str) -> str:
    normalized = value.strip()
    if not _S3_BUCKET_NAME.fullmatch(normalized):
        raise InvalidConfiguration(
            "Object-storage bucket must be 3-63 lowercase letters, numbers, or hyphens"
        )
    return normalized


def validate_aws_region(value: str) -> str:
    normalized = value.strip().casefold()
    if (
        len(normalized) > 32
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+){2,3}", normalized)
        or normalized.startswith(("cn-", "us-iso-", "us-isob-"))
    ):
        raise InvalidConfiguration(
            "Amazon S3 region must be a supported standard AWS region code"
        )
    return normalized


def _aws4_sign(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode(), hashlib.sha256).digest()


def _r2_authorization_headers(
    credentials: dict[str, object],
    *,
    method: str,
    host: str,
    canonical_uri: str,
    body: bytes,
    now: datetime | None = None,
) -> dict[str, str]:
    access_key_id = credentials.get("access_key_id")
    secret_access_key = credentials.get("secret_access_key")
    if not isinstance(access_key_id, str) or not access_key_id:
        raise ProviderUnavailable("Cloudflare R2 access key is unavailable")
    if not isinstance(secret_access_key, str) or not secret_access_key:
        raise ProviderUnavailable("Cloudflare R2 secret access key is unavailable")

    instant = now or datetime.now(UTC)
    amz_date = instant.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = instant.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/auto/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    date_key = _aws4_sign(f"AWS4{secret_access_key}".encode(), date_stamp)
    region_key = _aws4_sign(date_key, "auto")
    service_key = _aws4_sign(region_key, "s3")
    signing_key = _aws4_sign(service_key, "aws4_request")
    signature = hmac.new(
        signing_key,
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Authorization": (
            "AWS4-HMAC-SHA256 "
            f"Credential={access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }


def _aws_s3_authorization_headers(
    credentials: dict[str, object],
    *,
    method: str,
    host: str,
    canonical_uri: str,
    region: str,
    body: bytes,
    now: datetime | None = None,
) -> dict[str, str]:
    access_key_id = credentials.get("access_key_id")
    secret_access_key = credentials.get("secret_access_key")
    session_token = credentials.get("session_token")
    if not isinstance(access_key_id, str) or not access_key_id:
        raise ProviderUnavailable("Amazon S3 access key is unavailable")
    if not isinstance(secret_access_key, str) or not secret_access_key:
        raise ProviderUnavailable("Amazon S3 secret access key is unavailable")
    if session_token is not None and (
        not isinstance(session_token, str) or not session_token
    ):
        raise InvalidConfiguration("Stored Amazon S3 session token is invalid")

    safe_region = validate_aws_region(region)
    instant = now or datetime.now(UTC)
    amz_date = instant.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = instant.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_header_lines = [
        f"host:{host}",
        f"x-amz-content-sha256:{payload_hash}",
        f"x-amz-date:{amz_date}",
    ]
    signed_header_names = ["host", "x-amz-content-sha256", "x-amz-date"]
    if isinstance(session_token, str):
        canonical_header_lines.append(f"x-amz-security-token:{session_token}")
        signed_header_names.append("x-amz-security-token")

    canonical_headers = "\n".join(canonical_header_lines) + "\n"
    signed_headers = ";".join(signed_header_names)
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{safe_region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    date_key = _aws4_sign(f"AWS4{secret_access_key}".encode(), date_stamp)
    region_key = _aws4_sign(date_key, safe_region)
    service_key = _aws4_sign(region_key, "s3")
    signing_key = _aws4_sign(service_key, "aws4_request")
    signature = hmac.new(
        signing_key,
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Authorization": (
            "AWS4-HMAC-SHA256 "
            f"Credential={access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if isinstance(session_token, str):
        headers["x-amz-security-token"] = session_token
    return headers


async def _aws_s3_request(
    credentials: dict[str, object],
    *,
    method: str,
    region: str,
    bucket: str,
    key: str | None = None,
    body: bytes = b"",
    content_type: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    safe_region = validate_aws_region(region)
    safe_bucket = validate_s3_bucket_name(bucket)
    host = f"{safe_bucket}.s3.{safe_region}.amazonaws.com"
    canonical_uri = "/"
    if key is not None:
        canonical_uri = f"/{quote(key, safe='/-_.~')}"
    headers = _aws_s3_authorization_headers(
        credentials,
        method=method,
        host=host,
        canonical_uri=canonical_uri,
        region=safe_region,
        body=body,
    )
    if content_type is not None:
        headers["Content-Type"] = content_type
    return await _request(
        transport,
        method,
        f"https://{host}{canonical_uri}",
        headers=headers,
        content=body,
    )


async def probe_aws_s3_bucket(
    credentials: dict[str, object],
    *,
    region: str,
    bucket: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    response = await _aws_s3_request(
        credentials,
        method="HEAD",
        region=region,
        bucket=bucket,
        transport=transport,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"Amazon S3 bucket probe failed with HTTP {response.status_code}"
        )
    safe_region = validate_aws_region(region)
    safe_bucket = validate_s3_bucket_name(bucket)
    return ProviderOperationResult(
        external_id=safe_bucket,
        metadata={
            "bucket": safe_bucket,
            "region": safe_region,
            "endpoint_host": f"{safe_bucket}.s3.{safe_region}.amazonaws.com",
        },
    )


async def put_aws_s3_object(
    credentials: dict[str, object],
    *,
    region: str,
    bucket: str,
    name: str,
    content: str,
    mime_type: str,
    prefix: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    if mime_type not in _ALLOWED_DRIVE_MIME_TYPES:
        raise InvalidConfiguration("Amazon S3 export MIME type is not allowed")
    media = content.encode()
    if len(media) > 5_000_000:
        raise InvalidConfiguration("Amazon S3 export is limited to 5 MB")

    clean_name = "/".join(
        segment.strip()
        for segment in name.replace("\\", "/").split("/")
        if segment.strip()
    )
    if (
        not clean_name
        or len(clean_name) > 1024
        or ".." in clean_name.split("/")
    ):
        raise InvalidConfiguration("Amazon S3 object name is invalid")
    clean_prefix = prefix.strip("/")
    key = f"{clean_prefix}/{clean_name}" if clean_prefix else clean_name

    response = await _aws_s3_request(
        credentials,
        method="PUT",
        region=region,
        bucket=bucket,
        key=key,
        body=media,
        content_type=mime_type,
        transport=transport,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"Amazon S3 upload failed with HTTP {response.status_code}"
        )
    return ProviderOperationResult(
        external_id=key,
        metadata={
            "bucket": validate_s3_bucket_name(bucket),
            "region": validate_aws_region(region),
            "key": key,
            "etag": response.headers.get("etag"),
        },
    )


async def _r2_request(
    credentials: dict[str, object],
    *,
    method: str,
    endpoint_url: str,
    bucket: str,
    key: str | None = None,
    body: bytes = b"",
    content_type: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    endpoint = validate_r2_endpoint_url(endpoint_url)
    safe_bucket = validate_s3_bucket_name(bucket)
    host = urlsplit(endpoint).hostname
    assert host is not None
    canonical_uri = f"/{quote(safe_bucket, safe='-_.~')}"
    if key is not None:
        canonical_uri += f"/{quote(key, safe='/-_.~')}"
    headers = _r2_authorization_headers(
        credentials,
        method=method,
        host=host,
        canonical_uri=canonical_uri,
        body=body,
    )
    if content_type is not None:
        headers["Content-Type"] = content_type
    return await _request(
        transport,
        method,
        f"{endpoint}{canonical_uri}",
        headers=headers,
        content=body,
    )


async def probe_cloudflare_r2_bucket(
    credentials: dict[str, object],
    *,
    endpoint_url: str,
    bucket: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    response = await _r2_request(
        credentials,
        method="HEAD",
        endpoint_url=endpoint_url,
        bucket=bucket,
        transport=transport,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"Cloudflare R2 bucket probe failed with HTTP {response.status_code}"
        )
    endpoint = validate_r2_endpoint_url(endpoint_url)
    return ProviderOperationResult(
        external_id=validate_s3_bucket_name(bucket),
        metadata={
            "bucket": validate_s3_bucket_name(bucket),
            "endpoint_host": urlsplit(endpoint).hostname,
        },
    )


async def put_cloudflare_r2_object(
    credentials: dict[str, object],
    *,
    endpoint_url: str,
    bucket: str,
    name: str,
    content: str,
    mime_type: str,
    prefix: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    if mime_type not in _ALLOWED_DRIVE_MIME_TYPES:
        raise InvalidConfiguration("R2 export MIME type is not allowed")
    media = content.encode()
    if len(media) > 5_000_000:
        raise InvalidConfiguration("R2 export is limited to 5 MB")

    clean_name = "/".join(
        segment.strip()
        for segment in name.replace("\\", "/").split("/")
        if segment.strip()
    )
    if (
        not clean_name
        or len(clean_name) > 1024
        or ".." in clean_name.split("/")
    ):
        raise InvalidConfiguration("R2 object name is invalid")
    clean_prefix = prefix.strip("/")
    key = f"{clean_prefix}/{clean_name}" if clean_prefix else clean_name

    response = await _r2_request(
        credentials,
        method="PUT",
        endpoint_url=endpoint_url,
        bucket=bucket,
        key=key,
        body=media,
        content_type=mime_type,
        transport=transport,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"Cloudflare R2 upload failed with HTTP {response.status_code}"
        )
    return ProviderOperationResult(
        external_id=key,
        metadata={
            "bucket": validate_s3_bucket_name(bucket),
            "key": key,
            "etag": response.headers.get("etag"),
        },
    )


def _validate_ogc_bbox(value: object) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 4
        or not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
    ):
        raise InvalidConfiguration("OGC bbox must contain four numeric WGS84 values")
    min_x, min_y, max_x, max_y = (float(item) for item in value)
    if (
        not -180 <= min_x <= 180
        or not -180 <= max_x <= 180
        or not -90 <= min_y <= 90
        or not -90 <= max_y <= 90
        or min_x > max_x
        or min_y > max_y
    ):
        raise InvalidConfiguration("OGC bbox is outside the WGS84 bounds")
    return ",".join(str(item) for item in (min_x, min_y, max_x, max_y))


def _validate_ogc_datetime(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 128 or not _OGC_DATETIME.fullmatch(value):
        raise InvalidConfiguration("OGC datetime is invalid")
    return value


async def query_ogc_features(
    *,
    base_url: str,
    collection_id: str,
    limit: int,
    bbox: object = None,
    datetime_value: object = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise InvalidConfiguration("OGC limit must be an integer between 1 and 1000")
    base = validate_ogc_api_base_url(base_url)
    collection = validate_ogc_collection_id(collection_id)
    if transport is None:
        await validate_public_ogc_destination(base)

    params: dict[str, str] = {"limit": str(limit)}
    safe_bbox = _validate_ogc_bbox(bbox)
    if safe_bbox is not None:
        params["bbox"] = safe_bbox
    safe_datetime = _validate_ogc_datetime(datetime_value)
    if safe_datetime is not None:
        params["datetime"] = safe_datetime

    endpoint = (
        f"{base}/collections/{quote(collection, safe='-._~')}/items"
    )
    response = await _request_limited(
        transport,
        "GET",
        endpoint,
        max_bytes=5_000_000,
        headers={"Accept": "application/geo+json, application/json"},
        params=params,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"OGC API Features query failed with HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable("OGC API Features returned invalid JSON") from error
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ProviderUnavailable("OGC API Features must return a FeatureCollection")
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise ProviderUnavailable("OGC API Features response has invalid features")
    for feature in raw_features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ProviderUnavailable("OGC API Features returned an invalid feature")
    features = raw_features[:limit]

    data: dict[str, object] = {
        "type": "FeatureCollection",
        "features": features,
    }
    bbox_value = payload.get("bbox")
    if isinstance(bbox_value, list):
        data["bbox"] = bbox_value
    return ProviderQueryResult(
        data=data,
        metadata={
            "source_host": urlsplit(base).hostname,
            "collection_id": collection,
            "feature_count": len(features),
            "source_feature_count": len(raw_features),
            "truncated": len(raw_features) > len(features),
            "number_matched": payload.get("numberMatched"),
            "number_returned": payload.get("numberReturned"),
        },
    )


async def query_stac_items(
    *,
    base_url: str,
    collection_id: str,
    limit: int,
    bbox: object = None,
    datetime_value: object = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise InvalidConfiguration("STAC limit must be an integer between 1 and 1000")
    base = validate_stac_api_base_url(base_url)
    collection = validate_stac_collection_id(collection_id)
    if transport is None:
        await validate_public_stac_destination(base)

    params: dict[str, str] = {
        "collections": collection,
        "limit": str(limit),
    }
    safe_bbox = _validate_ogc_bbox(bbox)
    if safe_bbox is not None:
        params["bbox"] = safe_bbox
    safe_datetime = _validate_ogc_datetime(datetime_value)
    if safe_datetime is not None:
        params["datetime"] = safe_datetime

    response = await _request_limited(
        transport,
        "GET",
        f"{base}/search",
        max_bytes=5_000_000,
        headers={"Accept": "application/geo+json, application/json"},
        params=params,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"STAC API item search failed with HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable("STAC API returned invalid JSON") from error
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ProviderUnavailable("STAC API search must return a FeatureCollection")
    raw_items = payload.get("features")
    if not isinstance(raw_items, list):
        raise ProviderUnavailable("STAC API search response has invalid features")

    for item in raw_items:
        if (
            not isinstance(item, dict)
            or item.get("type") != "Feature"
            or not isinstance(item.get("id"), str)
            or not isinstance(item.get("stac_version"), str)
        ):
            raise ProviderUnavailable("STAC API returned an invalid STAC Item")
    items = raw_items[:limit]

    data: dict[str, object] = {
        "type": "FeatureCollection",
        "features": items,
    }
    bbox_value = payload.get("bbox")
    if isinstance(bbox_value, list):
        data["bbox"] = bbox_value
    return ProviderQueryResult(
        data=data,
        metadata={
            "source_host": urlsplit(base).hostname,
            "collection_id": collection,
            "item_count": len(items),
            "source_item_count": len(raw_items),
            "truncated": len(raw_items) > len(items),
            "number_matched": payload.get("numberMatched"),
            "number_returned": payload.get("numberReturned"),
        },
    )


def validate_nws_forecast_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    try:
        port = parsed.port
    except ValueError as error:
        raise ProviderUnavailable("NWS returned an invalid forecast URL") from error
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").casefold() != "api.weather.gov"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
        or not _NWS_FORECAST_PATH.fullmatch(parsed.path)
    ):
        raise ProviderUnavailable("NWS returned an invalid forecast URL")
    return normalized


def _validate_weather_coordinates(latitude: object, longitude: object) -> tuple[float, float]:
    if (
        not isinstance(latitude, (int, float))
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or isinstance(longitude, bool)
    ):
        raise InvalidConfiguration(
            "NWS forecast latitude and longitude must be numeric"
        )
    lat = round(float(latitude), 4)
    lon = round(float(longitude), 4)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise InvalidConfiguration(
            "NWS forecast coordinates are outside valid latitude/longitude bounds"
        )
    return lat, lon


async def query_nws_forecast(
    *,
    latitude: object,
    longitude: object,
    max_periods: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    if (
        not isinstance(max_periods, int)
        or isinstance(max_periods, bool)
        or not 1 <= max_periods <= 14
    ):
        raise InvalidConfiguration(
            "NWS forecast max_periods must be an integer between 1 and 14"
        )
    lat, lon = _validate_weather_coordinates(latitude, longitude)
    headers = {
        "Accept": "application/geo+json",
        "User-Agent": _NWS_USER_AGENT,
    }

    point_response = await _request_limited(
        transport,
        "GET",
        f"{_NWS_ROOT}/points/{lat:.4f},{lon:.4f}",
        max_bytes=1_000_000,
        headers=headers,
    )
    if point_response.status_code < 200 or point_response.status_code >= 300:
        raise ProviderUnavailable(
            f"NWS point lookup failed with HTTP {point_response.status_code}"
        )
    try:
        point_payload = point_response.json()
    except ValueError as error:
        raise ProviderUnavailable("NWS point lookup returned invalid JSON") from error
    if not isinstance(point_payload, dict):
        raise ProviderUnavailable("NWS point lookup returned an invalid response")
    properties = point_payload.get("properties")
    if not isinstance(properties, dict):
        raise ProviderUnavailable("NWS point lookup is missing properties")
    forecast_url = properties.get("forecast")
    if not isinstance(forecast_url, str):
        raise ProviderUnavailable("NWS point lookup is missing forecast URL")
    forecast_url = validate_nws_forecast_url(forecast_url)

    forecast_response = await _request_limited(
        transport,
        "GET",
        forecast_url,
        max_bytes=2_000_000,
        headers=headers,
    )
    if forecast_response.status_code < 200 or forecast_response.status_code >= 300:
        raise ProviderUnavailable(
            f"NWS forecast query failed with HTTP {forecast_response.status_code}"
        )
    try:
        forecast_payload = forecast_response.json()
    except ValueError as error:
        raise ProviderUnavailable("NWS forecast returned invalid JSON") from error
    if not isinstance(forecast_payload, dict):
        raise ProviderUnavailable("NWS forecast returned an invalid response")
    forecast_properties = forecast_payload.get("properties")
    if not isinstance(forecast_properties, dict):
        raise ProviderUnavailable("NWS forecast is missing properties")
    raw_periods = forecast_properties.get("periods")
    if not isinstance(raw_periods, list):
        raise ProviderUnavailable("NWS forecast periods are invalid")
    periods: list[dict[str, object]] = []
    for period in raw_periods[:max_periods]:
        if not isinstance(period, dict):
            raise ProviderUnavailable("NWS forecast returned an invalid period")
        periods.append(period)

    data: dict[str, object] = {
        "periods": periods,
    }
    for key in ("updated", "units", "generatedAt"):
        value = forecast_properties.get(key)
        if value is not None:
            data[key] = value

    return ProviderQueryResult(
        data=data,
        metadata={
            "source_host": "api.weather.gov",
            "latitude": lat,
            "longitude": lon,
            "office": properties.get("gridId"),
            "grid_x": properties.get("gridX"),
            "grid_y": properties.get("gridY"),
            "period_count": len(periods),
            "source_period_count": len(raw_periods),
            "truncated": len(raw_periods) > len(periods),
        },
    )


async def probe_nws_api(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    response = await _request_limited(
        transport,
        "GET",
        f"{_NWS_ROOT}/points/39.7456,-97.0892",
        max_bytes=1_000_000,
        headers={
            "Accept": "application/geo+json",
            "User-Agent": _NWS_USER_AGENT,
        },
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"NWS API probe failed with HTTP {response.status_code}"
        )
    return ProviderOperationResult(
        external_id="api.weather.gov",
        metadata={"source_host": "api.weather.gov"},
    )


async def query_geojson_features(
    *,
    endpoint_url: str,
    max_features: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    if not isinstance(max_features, int) or isinstance(max_features, bool):
        raise InvalidConfiguration("GeoJSON max_features must be an integer")
    if not 1 <= max_features <= 1000:
        raise InvalidConfiguration("GeoJSON max_features must be between 1 and 1000")

    endpoint = validate_geojson_url(endpoint_url)
    if transport is None:
        await validate_public_geojson_destination(endpoint)

    response = await _request_limited(
        transport,
        "GET",
        endpoint,
        max_bytes=5_000_000,
        headers={"Accept": "application/geo+json, application/json"},
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"GeoJSON endpoint query failed with HTTP {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable("GeoJSON endpoint returned invalid JSON") from error
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ProviderUnavailable(
            "GeoJSON endpoint must return a FeatureCollection"
        )
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise ProviderUnavailable("GeoJSON FeatureCollection features must be a list")

    features: list[dict[str, object]] = []
    for feature in raw_features[:max_features]:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ProviderUnavailable("GeoJSON endpoint returned an invalid feature")
        features.append(feature)

    data: dict[str, object] = {
        "type": "FeatureCollection",
        "features": features,
    }
    bbox = payload.get("bbox")
    if isinstance(bbox, list):
        data["bbox"] = bbox

    hostname = urlsplit(endpoint).hostname
    return ProviderQueryResult(
        data=data,
        metadata={
            "source_host": hostname,
            "feature_count": len(features),
            "source_feature_count": len(raw_features),
            "truncated": len(raw_features) > len(features),
        },
    )


async def _request_limited(
    transport: httpx.AsyncBaseTransport | None,
    method: str,
    url: str,
    *,
    max_bytes: int,
    **kwargs,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=False,
            transport=transport,
        ) as client:
            async with client.stream(method, url, **kwargs) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > max_bytes:
                        raise ProviderUnavailable(
                            "Provider response exceeds the configured size limit"
                        )
                    content.extend(chunk)
                return httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=bytes(content),
                    request=response.request,
                )
    except ProviderUnavailable:
        raise
    except httpx.HTTPError as error:
        raise ProviderUnavailable("Provider delivery request failed") from error


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


async def send_resend_notification(
    *,
    api_key: str,
    sender: str,
    recipients: list[str],
    subject: str,
    text: str,
    request_id: UUID,
    connection_id: UUID,
    reply_to: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    normalized_text = text.strip()
    if not normalized_text:
        raise InvalidConfiguration("Operational email message cannot be empty")
    if len(normalized_text) > 10_000:
        raise InvalidConfiguration("Operational email message is limited to 10000 characters")
    if not api_key.strip():
        raise ProviderUnavailable("Operational Resend API key is unavailable")
    if not sender.strip() or "\n" in sender or "\r" in sender:
        raise InvalidConfiguration("Operational email sender is invalid")
    if not recipients or len(recipients) > 10:
        raise InvalidConfiguration("Operational email requires 1-10 recipients")
    if (
        not subject.strip()
        or len(subject.strip()) > 160
        or "\n" in subject
        or "\r" in subject
    ):
        raise InvalidConfiguration("Operational email subject is invalid")

    payload: dict[str, object] = {
        "from": sender.strip(),
        "to": recipients,
        "subject": subject.strip(),
        "text": normalized_text,
    }
    if reply_to:
        if "\n" in reply_to or "\r" in reply_to:
            raise InvalidConfiguration("Operational email reply-to is invalid")
        payload["reply_to"] = reply_to.strip()

    response = await _request(
        transport,
        "POST",
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "Idempotency-Key": (
                f"terrasatch-email/{connection_id}/{request_id}"
            )[:256],
        },
        json=payload,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"Operational email delivery failed with HTTP {response.status_code}"
        )
    try:
        data = response.json()
    except ValueError as error:
        raise ProviderUnavailable(
            "Operational email provider returned an invalid response"
        ) from error
    message_id = str(data.get("id") or "").strip() if isinstance(data, dict) else ""
    return ProviderOperationResult(
        external_id=message_id[:255] or None,
        metadata={
            "provider": "resend",
            "recipient_count": len(recipients),
        },
    )


async def send_teams_message(
    credentials: dict[str, object],
    *,
    text: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    normalized = text.strip()
    if not normalized:
        raise InvalidConfiguration("Microsoft Teams message cannot be empty")
    if len(normalized) > 4000:
        raise InvalidConfiguration("Microsoft Teams message is limited to 4000 characters")

    raw_url = credentials.get("webhook_url")
    if not isinstance(raw_url, str) or not raw_url:
        raise ProviderUnavailable("Microsoft Teams Workflows webhook is unavailable")
    url = validate_teams_workflow_url(raw_url)
    if transport is None:
        await validate_public_webhook_destination(
            url,
            label="Microsoft Teams",
            allowed_host_suffixes=_TEAMS_WEBHOOK_HOST_SUFFIXES,
        )

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": normalized,
                            "wrap": True,
                        }
                    ],
                },
            }
        ],
    }
    response = await _request(
        transport,
        "POST",
        url,
        json=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"Microsoft Teams webhook delivery failed with HTTP {response.status_code}"
        )
    return ProviderOperationResult(
        external_id=response.headers.get("x-ms-workflow-run-id"),
        metadata={
            "destination_host": urlsplit(url).hostname,
            "status_code": response.status_code,
        },
    )


async def send_webhook_notification(
    credentials: dict[str, object],
    *,
    text: str,
    request_id: UUID,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    normalized = text.strip()
    if not normalized:
        raise InvalidConfiguration("Webhook notification cannot be empty")
    if len(normalized) > 4000:
        raise InvalidConfiguration("Webhook notification is limited to 4000 characters")

    raw_url = credentials.get("webhook_url")
    if not isinstance(raw_url, str) or not raw_url:
        raise ProviderUnavailable("Webhook URL is unavailable")
    url = validate_generic_webhook_url(raw_url)
    if transport is None:
        await validate_public_webhook_destination(url, label="Generic")

    payload = {
        "type": "terrasatch.notification",
        "version": "1",
        "request_id": str(request_id),
        "text": normalized,
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Idempotency-Key": str(request_id),
        "X-TerraSatch-Event": "notification.send",
    }
    signing_secret = credentials.get("signing_secret")
    if signing_secret is not None:
        if not isinstance(signing_secret, str) or not signing_secret:
            raise InvalidConfiguration("Stored webhook signing secret is invalid")
        timestamp = str(int(time.time()))
        signature_payload = timestamp.encode() + b"." + body
        signature = hmac.new(
            signing_secret.encode(),
            signature_payload,
            hashlib.sha256,
        ).hexdigest()
        headers["X-TerraSatch-Timestamp"] = timestamp
        headers["X-TerraSatch-Signature"] = f"sha256={signature}"

    response = await _request(
        transport,
        "POST",
        url,
        content=body,
        headers=headers,
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderUnavailable(
            f"Webhook delivery failed with HTTP {response.status_code}"
        )
    external_id = response.headers.get("x-request-id") or response.headers.get(
        "x-correlation-id"
    )
    return ProviderOperationResult(
        external_id=external_id,
        metadata={
            "destination_host": urlsplit(url).hostname,
            "status_code": response.status_code,
            "signed": signing_secret is not None,
        },
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
    ).encode() + media + f"\r\n--{boundary}--\r\n".encode("ascii")

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


def _calendar_id(value: str | None) -> str:
    if value is None:
        return "primary"
    normalized = value.strip()
    if not normalized or len(normalized) > 512 or "/" in normalized:
        raise InvalidConfiguration("Calendar ID is invalid")
    return normalized


def _calendar_event_values(
    *,
    title: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
) -> tuple[str, datetime, datetime, str, str]:
    clean_title = " ".join(title.split())
    if not clean_title or len(clean_title) > 200:
        raise InvalidConfiguration(
            "Calendar event title must be between 1 and 200 characters"
        )
    if len(description) > 5000:
        raise InvalidConfiguration("Calendar event description is limited to 5000 characters")
    clean_location = " ".join(location.split())
    if len(clean_location) > 500:
        raise InvalidConfiguration("Calendar event location is limited to 500 characters")

    try:
        start_at = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_at = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidConfiguration(
            "Calendar event start and end must be ISO 8601 timestamps"
        ) from error
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise InvalidConfiguration(
            "Calendar event start and end must include a UTC offset"
        )
    if end_at <= start_at:
        raise InvalidConfiguration("Calendar event end must be after start")
    if end_at - start_at > timedelta(days=7):
        raise InvalidConfiguration("Calendar events are limited to 7 days")
    return clean_title, start_at, end_at, description, clean_location


async def create_google_calendar_event(
    credentials: dict[str, object],
    *,
    calendar_id: str | None,
    title: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    access_token = credentials.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ProviderUnavailable("Google Calendar access token is unavailable")
    (
        clean_title,
        start_at,
        end_at,
        clean_description,
        clean_location,
    ) = _calendar_event_values(
        title=title,
        start=start,
        end=end,
        description=description,
        location=location,
    )
    target_calendar = _calendar_id(calendar_id)
    payload: dict[str, object] = {
        "summary": clean_title,
        "start": {"dateTime": start_at.isoformat()},
        "end": {"dateTime": end_at.isoformat()},
    }
    if clean_description:
        payload["description"] = clean_description
    if clean_location:
        payload["location"] = clean_location

    response = await _request(
        transport,
        "POST",
        (
            "https://www.googleapis.com/calendar/v3/calendars/"
            f"{quote(target_calendar, safe='')}/events"
        ),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if response.status_code not in {200, 201}:
        raise ProviderUnavailable(
            f"Google Calendar event creation failed with HTTP {response.status_code}"
        )
    try:
        result = response.json()
    except ValueError as error:
        raise ProviderUnavailable(
            "Google Calendar returned an invalid event response"
        ) from error
    if not isinstance(result, dict) or not result.get("id"):
        raise ProviderUnavailable("Google Calendar did not return an event ID")
    return ProviderOperationResult(
        external_id=str(result["id"]),
        metadata={
            key: value
            for key, value in {
                "calendar_id": target_calendar,
                "event_id": result.get("id"),
                "html_link": result.get("htmlLink"),
                "status": result.get("status"),
            }.items()
            if value is not None
        },
    )


async def create_microsoft_calendar_event(
    credentials: dict[str, object],
    *,
    calendar_id: str | None,
    title: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderOperationResult:
    access_token = credentials.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ProviderUnavailable("Microsoft Calendar access token is unavailable")
    (
        clean_title,
        start_at,
        end_at,
        clean_description,
        clean_location,
    ) = _calendar_event_values(
        title=title,
        start=start,
        end=end,
        description=description,
        location=location,
    )
    target_calendar = _calendar_id(calendar_id)
    if target_calendar == "primary":
        url = f"{_MICROSOFT_GRAPH_ROOT}/me/calendar/events"
    else:
        url = (
            f"{_MICROSOFT_GRAPH_ROOT}/me/calendars/"
            f"{quote(target_calendar, safe='')}/events"
        )
    start_utc = start_at.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    end_utc = end_at.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    payload: dict[str, object] = {
        "subject": clean_title,
        "start": {"dateTime": start_utc, "timeZone": "UTC"},
        "end": {"dateTime": end_utc, "timeZone": "UTC"},
    }
    if clean_description:
        payload["body"] = {"contentType": "text", "content": clean_description}
    if clean_location:
        payload["location"] = {"displayName": clean_location}

    response = await _request(
        transport,
        "POST",
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if response.status_code != 201:
        raise ProviderUnavailable(
            f"Microsoft Calendar event creation failed with HTTP {response.status_code}"
        )
    try:
        result = response.json()
    except ValueError as error:
        raise ProviderUnavailable(
            "Microsoft Calendar returned an invalid event response"
        ) from error
    if not isinstance(result, dict) or not result.get("id"):
        raise ProviderUnavailable("Microsoft Calendar did not return an event ID")
    return ProviderOperationResult(
        external_id=str(result["id"]),
        metadata={
            key: value
            for key, value in {
                "calendar_id": target_calendar,
                "event_id": result.get("id"),
                "web_link": result.get("webLink"),
                "is_cancelled": result.get("isCancelled"),
            }.items()
            if value is not None
        },
    )


async def query_public_arcgis_features(
    *,
    layer_url: str,
    where: str = "1=1",
    out_fields: list[str] | None = None,
    return_geometry: bool = True,
    result_record_count: int = 100,
    result_offset: int = 0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProviderQueryResult:
    normalized_layer = validate_public_arcgis_feature_layer_url(layer_url)
    if transport is None:
        await validate_public_arcgis_feature_layer_destination(normalized_layer)

    normalized_where = " ".join(where.split()).strip()
    if not normalized_where or len(normalized_where) > 2000:
        raise InvalidConfiguration(
            "ArcGIS where clause must be between 1 and 2000 characters"
        )

    fields = out_fields or ["*"]
    if not fields or len(fields) > 50:
        raise InvalidConfiguration(
            "ArcGIS out_fields must contain between 1 and 50 fields"
        )
    normalized_fields: list[str] = []
    for field in fields:
        candidate = field.strip()
        if candidate != "*" and not _ARCGIS_FIELD.fullmatch(candidate):
            raise InvalidConfiguration(
                "ArcGIS out_fields contains an invalid field name"
            )
        normalized_fields.append(candidate)

    if not 1 <= result_record_count <= 200:
        raise InvalidConfiguration(
            "ArcGIS queries are limited to 200 features per request"
        )
    if not 0 <= result_offset <= 1_000_000:
        raise InvalidConfiguration(
            "ArcGIS result offset is outside the allowed range"
        )

    response = await _request_limited(
        transport,
        "POST",
        f"{normalized_layer}/query",
        max_bytes=2_000_000,
        data={
            "f": "json",
            "where": normalized_where,
            "outFields": ",".join(normalized_fields),
            "returnGeometry": "true" if return_geometry else "false",
            "resultRecordCount": str(result_record_count),
            "resultOffset": str(result_offset),
        },
    )
    if response.status_code >= 400:
        raise ProviderUnavailable(
            f"Public ArcGIS Enterprise query failed with HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable(
            "Public ArcGIS Enterprise returned an invalid feature response"
        ) from error
    if not isinstance(payload, dict):
        raise ProviderUnavailable(
            "Public ArcGIS Enterprise returned an invalid feature response"
        )
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        code = error_payload.get("code")
        message = error_payload.get("message") or "query_failed"
        raise ProviderUnavailable(
            f"Public ArcGIS Enterprise query failed ({code}: {message})"
        )

    features = payload.get("features")
    if features is not None and not isinstance(features, list):
        raise ProviderUnavailable(
            "Public ArcGIS Enterprise returned an invalid feature collection"
        )
    feature_count = len(features or [])
    metadata: dict[str, object] = {
        "feature_count": feature_count,
        "layer_url": normalized_layer,
        "return_geometry": return_geometry,
        "source_host": urlsplit(normalized_layer).hostname,
    }
    if payload.get("geometryType"):
        metadata["geometry_type"] = payload["geometryType"]
    if payload.get("exceededTransferLimit") is not None:
        metadata["exceeded_transfer_limit"] = bool(
            payload["exceededTransferLimit"]
        )
    return ProviderQueryResult(data=payload, metadata=metadata)


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
    site_id: str | None = None,
    drive_id: str | None = None,
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
    if drive_id:
        clean_drive_id = drive_id.strip()
        if not clean_drive_id or len(clean_drive_id) > 512 or "/" in clean_drive_id:
            raise InvalidConfiguration("Microsoft drive_id is invalid")
        url = (
            f"{_MICROSOFT_GRAPH_ROOT}/drives/"
            f"{quote(clean_drive_id, safe='')}/root:/{encoded_path}:/content"
        )
    elif site_id:
        clean_site_id = site_id.strip()
        if (
            not clean_site_id
            or len(clean_site_id) > 512
            or "/" in clean_site_id
            or "://" in clean_site_id
        ):
            raise InvalidConfiguration("Microsoft site_id is invalid")
        url = (
            f"{_MICROSOFT_GRAPH_ROOT}/sites/"
            f"{quote(clean_site_id, safe=',')}/drive/root:/{encoded_path}:/content"
        )
    else:
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
        "target": (
            "sharepoint_drive"
            if drive_id
            else "sharepoint_site"
            if site_id
            else "onedrive"
        ),
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
