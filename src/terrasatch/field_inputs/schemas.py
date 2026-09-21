"""Validated contracts for Garmin and native mobile field inputs."""

from __future__ import annotations

import re
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GarminAddress(BaseModel):
    model_config = ConfigDict(extra="ignore")

    address: str = Field(min_length=1, max_length=320)


class GarminPoint(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude: float | None = None
    gpsFix: int | None = Field(default=None, ge=0, le=3)
    course: float | None = Field(default=None, ge=0, le=360)
    speed: float | None = Field(default=None, ge=0)


class GarminStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    autonomous: int | None = Field(default=None, ge=0, le=1)
    lowBattery: int | None = Field(default=None, ge=0, le=2)
    intervalChange: int | None = Field(default=None, ge=0)
    resetDetected: int | None = Field(default=None, ge=0, le=1)


class GarminEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    imei: str = Field(min_length=15, max_length=255)
    messageCode: int = Field(ge=0, le=10_000)
    freeText: str | None = Field(default=None, max_length=20_000)
    timeStamp: int | None = Field(default=None, ge=0)
    pingbackReceived: int | None = Field(default=None, ge=0)
    pingbackResponded: int | None = Field(default=None, ge=0)
    addresses: list[GarminAddress] = Field(default_factory=list, max_length=64)
    point: GarminPoint | None = None
    status: GarminStatus | None = None
    payload: str | None = Field(default=None, max_length=16_000_000)
    transportMode: Literal["Satellite", "Internet"] | None = None
    mediaBytes: str | None = Field(default=None, max_length=16_000_000)
    mediaId: str | None = Field(default=None, max_length=128)
    mediaType: Literal["image/avif", "audio/ogg"] | None = None
    transcription: str | None = Field(default=None, max_length=20_000)

    @field_validator("imei")
    @classmethod
    def validate_imei_list(cls, value: str) -> str:
        normalized = ",".join(part.strip() for part in value.split(",") if part.strip())
        parts = normalized.split(",")
        if not parts or any(not re.fullmatch(r"[0-9]{15}", part) for part in parts):
            raise ValueError("imei must contain one or more 15-digit identifiers")
        return normalized

    @field_validator("freeText", "transcription", "mediaId", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class GarminIpcPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    version: Literal["2.0", "3.0", "4.0"] = Field(alias="Version")
    events: list[GarminEvent] = Field(alias="Events", min_length=1, max_length=100)


class GarminIngestResponse(BaseModel):
    accepted: int
    duplicates: int
    transmissions: list[UUID]
    operational_events: int


class MobileObservationRequest(BaseModel):
    """Native TerraSatch mobile observation; binary media is uploaded separately."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    site_id: UUID
    agent_id: UUID | None = None
    channel_id: UUID | None = None
    client_message_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=20_000)
    captured_at: str | None = Field(default=None, max_length=40)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    altitude_m: float | None = None
    accuracy_m: float | None = Field(default=None, ge=0, le=100_000)
    source_kind: Literal["note", "voice_transcript", "photo_note"] = "note"
    media_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("client_message_id", "text", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def coordinates_are_paired(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self
