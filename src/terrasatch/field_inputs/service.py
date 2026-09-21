"""Canonical ingestion for Garmin inReach and native mobile field inputs."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.errors import AuthenticationFailed, InvalidConfiguration, ResourceNotFound
from terrasatch.integrations.models import IntegrationConnection, IntegrationStatus
from terrasatch.integrations.oauth_service import active_credentials
from terrasatch.radio.models import OperationalEvent, Transmission
from terrasatch.radio.schemas import RfMetadata, TransmissionCreateRequest
from terrasatch.radio.service import ingest_transmission

if TYPE_CHECKING:
    from terrasatch.field_inputs.schemas import (
        GarminEvent,
        GarminIpcPayload,
        MobileObservationRequest,
    )


_GARMIN_MESSAGE_LABELS = {
    0: "position report",
    2: "locate response",
    3: "free text message",
    4: "SOS declared",
    6: "SOS confirmed",
    7: "SOS cancelled",
    8: "reference point",
    10: "tracking started",
    11: "tracking interval changed",
    12: "tracking stopped",
    14: "preset message 1",
    15: "preset message 2",
    16: "preset message 3",
    17: "map share",
    20: "mail check",
    21: "device alive check",
    65: "pingback message",
    3099: "canned message",
}


@dataclass(slots=True)
class FieldIngestBatch:
    transmissions: list[Transmission]
    events: list[OperationalEvent]
    duplicates: int


def _garmin_event_imeis(event: GarminEvent) -> list[str]:
    return [part for part in event.imei.split(",") if part]


def _garmin_point(event: GarminEvent) -> tuple[float, float] | None:
    point = event.point
    if point is None:
        return None
    if point.latitude == 0 and point.longitude == 0:
        return None
    return point.latitude, point.longitude


def _garmin_text(event: GarminEvent) -> str:
    parts: list[str] = []
    if event.freeText:
        parts.append(event.freeText)
    if event.transcription and event.transcription not in parts:
        parts.append(event.transcription)

    if not parts:
        if 24 <= event.messageCode <= 63:
            label = f"pre-defined message {event.messageCode}"
        else:
            label = _GARMIN_MESSAGE_LABELS.get(
                event.messageCode,
                f"event code {event.messageCode}",
            )
        parts.append(f"Garmin inReach {label}")

    point = _garmin_point(event)
    if point is not None:
        latitude, longitude = point
        location_text = f"{latitude:.5f}, {longitude:.5f}"
        if location_text not in " ".join(parts):
            parts.append(f"Location {location_text}")

    return " — ".join(parts)


def _garmin_started_at(event: GarminEvent) -> datetime | None:
    if event.timeStamp is None or event.timeStamp <= 0:
        return None
    try:
        return datetime.fromtimestamp(event.timeStamp / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _garmin_source_message_id(event: GarminEvent) -> str:
    media_hash = (
        hashlib.sha256(event.mediaBytes.encode("utf-8")).hexdigest()
        if event.mediaBytes
        else None
    )
    payload_hash = (
        hashlib.sha256(event.payload.encode("utf-8")).hexdigest()
        if event.payload
        else None
    )
    canonical = {
        "imei": event.imei,
        "messageCode": event.messageCode,
        "timeStamp": event.timeStamp,
        "freeText": event.freeText,
        "transcription": event.transcription,
        "mediaId": event.mediaId,
        "mediaType": event.mediaType,
        "mediaHash": media_hash,
        "payloadHash": payload_hash,
        "point": event.point.model_dump(exclude_none=True) if event.point else None,
        "transportMode": event.transportMode,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    imei = _garmin_event_imeis(event)[0]
    timestamp = event.timeStamp or 0
    return f"garmin:{imei}:{timestamp}:{event.messageCode}:{digest[:24]}"


def _garmin_rf_metadata(payload: GarminIpcPayload, event: GarminEvent) -> RfMetadata:
    garmin: dict[str, object] = {
        "schema_version": payload.version,
        "imeis": _garmin_event_imeis(event),
        "message_code": event.messageCode,
        "transport_mode": event.transportMode,
        "recipient_count": len(event.addresses),
    }
    if event.point is not None:
        garmin["point"] = event.point.model_dump(exclude_none=True)
    if event.status is not None:
        garmin["status"] = event.status.model_dump(exclude_none=True)
    if event.mediaId or event.mediaType or event.mediaBytes or event.transcription:
        garmin["media"] = {
            "id": event.mediaId,
            "type": event.mediaType,
            "base64_characters": len(event.mediaBytes or ""),
            "transcription_present": bool(event.transcription),
        }
    if event.payload:
        garmin["binary_payload_characters"] = len(event.payload)

    return RfMetadata.model_validate(
        {
            "receiver_name": "Garmin inReach Portal Connect",
            "source_type": "garmin_inreach",
            "garmin": garmin,
        }
    )


def _uuid_from_configuration(
    configuration: dict[str, object],
    key: str,
    *,
    required: bool,
) -> UUID | None:
    value = configuration.get(key)
    if value is None:
        if required:
            raise InvalidConfiguration(f"Garmin {key} is not configured")
        return None
    if not isinstance(value, str):
        raise InvalidConfiguration(f"Garmin {key} is invalid")
    try:
        return UUID(value)
    except ValueError as error:
        raise InvalidConfiguration(f"Garmin {key} is invalid") from error


async def resolve_garmin_connection(
    session: AsyncSession,
    *,
    connection_id: UUID,
) -> IntegrationConnection:
    connection = await session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.provider == "garmin",
            IntegrationConnection.status == IntegrationStatus.CONNECTED.value,
            IntegrationConnection.enabled.is_(True),
        )
    )
    if connection is None:
        raise ResourceNotFound("Garmin inReach connection was not found")
    return connection


async def authenticate_garmin_connection(
    session: AsyncSession,
    settings: Settings,
    *,
    connection: IntegrationConnection,
    provided_token: str | None,
) -> None:
    if not provided_token:
        raise AuthenticationFailed("Garmin inReach authorization is required")
    credentials, _credential = await active_credentials(
        session,
        settings,
        connection=connection,
    )
    expected = credentials.get("static_token")
    if (
        not isinstance(expected, str)
        or not expected
        or not secrets.compare_digest(expected, provided_token)
    ):
        raise AuthenticationFailed("Garmin inReach authorization failed")


def _apply_source_point(events: list[OperationalEvent], event: GarminEvent) -> None:
    point = _garmin_point(event)
    if point is None:
        return
    latitude, longitude = point
    elevation_ft = None
    if event.point is not None and event.point.altitude is not None:
        elevation_ft = round(event.point.altitude * 3.28084)

    for item in events:
        if item.latitude is None:
            item.latitude = latitude
        if item.longitude is None:
            item.longitude = longitude
        if item.elevation_ft is None and elevation_ft is not None:
            item.elevation_ft = elevation_ft
        item.data = {
            **dict(item.data or {}),
            "source_point": {
                "provider": "garmin_inreach",
                "latitude": latitude,
                "longitude": longitude,
                "altitude_m": event.point.altitude if event.point else None,
                "gps_fix": event.point.gpsFix if event.point else None,
            },
        }


async def ingest_garmin_payload(
    session: AsyncSession,
    settings: Settings,
    *,
    connection: IntegrationConnection,
    payload: GarminIpcPayload,
) -> FieldIngestBatch:
    configuration = dict(connection.configuration or {})
    site_id = _uuid_from_configuration(configuration, "site_id", required=True)
    assert site_id is not None
    agent_id = _uuid_from_configuration(configuration, "agent_id", required=False)
    channel_id = _uuid_from_configuration(configuration, "channel_id", required=False)

    allowed_raw = configuration.get("allowed_imeis", [])
    if not isinstance(allowed_raw, list) or not all(
        isinstance(item, str) for item in allowed_raw
    ):
        raise InvalidConfiguration("Garmin allowed_imeis configuration is invalid")
    allowed_imeis = set(allowed_raw)

    transmissions: list[Transmission] = []
    operational_events: list[OperationalEvent] = []
    duplicates = 0

    for event in payload.events:
        event_imeis = set(_garmin_event_imeis(event))
        if allowed_imeis and not event_imeis.intersection(allowed_imeis):
            raise AuthenticationFailed("Garmin inReach device is not approved")

        text = _garmin_text(event)
        transmission_payload = TransmissionCreateRequest(
            site_id=site_id,
            agent_id=agent_id,
            channel_id=channel_id,
            text=text,
            source="garmin_inreach",
            source_message_id=_garmin_source_message_id(event),
            started_at=_garmin_started_at(event),
            transcript_provider=(
                "garmin_inreach_transcription"
                if event.transcription
                else "garmin_inreach_text"
            ),
            transcript_language="en",
            transcript_confidence=1.0 if event.freeText else None,
            rf_metadata=_garmin_rf_metadata(payload, event),
        )
        transmission, _transcript, events, duplicate = await ingest_transmission(
            session,
            settings=settings,
            organization_id=connection.organization_id,
            payload=transmission_payload,
        )
        if not duplicate:
            _apply_source_point(events, event)
        transmissions.append(transmission)
        operational_events.extend(events)
        duplicates += int(duplicate)

    await session.flush()
    return FieldIngestBatch(
        transmissions=transmissions,
        events=operational_events,
        duplicates=duplicates,
    )


async def ingest_mobile_observation(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    user_id: UUID,
    payload: MobileObservationRequest,
):
    """Feed an authenticated native mobile observation into canonical ingest."""

    rf_metadata = RfMetadata.model_validate(
        {
            "receiver_name": "TerraSatch Mobile",
            "source_type": "terrasatch_mobile",
            "mobile": {
                "submitted_by_user_id": str(user_id),
                "source_kind": payload.source_kind,
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "altitude_m": payload.altitude_m,
                "accuracy_m": payload.accuracy_m,
                "media_ids": payload.media_ids,
            },
        }
    )
    transmission_payload = TransmissionCreateRequest(
        site_id=payload.site_id,
        agent_id=payload.agent_id,
        channel_id=payload.channel_id,
        text=payload.text,
        source="terrasatch_mobile",
        source_message_id=f"mobile:{user_id}:{payload.client_message_id}",
        started_at=payload.captured_at,
        transcript_provider=(
            "mobile_voice_transcript"
            if payload.source_kind == "voice_transcript"
            else "submitted_text"
        ),
        transcript_language="en",
        rf_metadata=rf_metadata,
    )
    transmission, transcript, events, duplicate = await ingest_transmission(
        session,
        settings=settings,
        organization_id=organization_id,
        payload=transmission_payload,
    )
    if not duplicate and payload.latitude is not None and payload.longitude is not None:
        for item in events:
            if item.latitude is None:
                item.latitude = payload.latitude
            if item.longitude is None:
                item.longitude = payload.longitude
            if item.elevation_ft is None and payload.altitude_m is not None:
                item.elevation_ft = round(payload.altitude_m * 3.28084)
            item.data = {
                **dict(item.data or {}),
                "source_point": {
                    "provider": "terrasatch_mobile",
                    "latitude": payload.latitude,
                    "longitude": payload.longitude,
                    "altitude_m": payload.altitude_m,
                    "accuracy_m": payload.accuracy_m,
                },
            }
        await session.flush()
    return transmission, transcript, events, duplicate
