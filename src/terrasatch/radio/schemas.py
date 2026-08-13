"""Pydantic contracts for radio-domain REST and realtime operations."""

from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    site_id: UUID
    profile: str = Field(default="general", min_length=1, max_length=100)


class AgentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    profile: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None


class AgentResponse(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: UUID
    name: str
    slug: str
    profile: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ChannelCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    site_id: UUID
    agent_id: UUID | None = None
    profile: str = Field(default="general", min_length=1, max_length=100)


class ChannelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    agent_id: UUID | None = None
    profile: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None


class ChannelResponse(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: UUID
    agent_id: UUID | None
    name: str
    slug: str
    profile: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CallsignCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    site_id: UUID | None = None
    team_id: UUID | None = None
    aliases: list[str] = Field(default_factory=list, max_length=32)


class CallsignUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    site_id: UUID | None = None
    team_id: UUID | None = None
    aliases: list[str] | None = Field(default=None, max_length=32)
    enabled: bool | None = None


class CallsignResponse(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: UUID | None
    team_id: UUID | None
    name: str
    aliases: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class TransmissionCreateRequest(BaseModel):
    site_id: UUID
    agent_id: UUID | None = None
    channel_id: UUID | None = None
    callsign: str | None = Field(default=None, max_length=255)
    text: str = Field(min_length=1, max_length=20_000)
    source: str = Field(default="api", min_length=1, max_length=64)
    source_message_id: str = Field(min_length=1, max_length=255)
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @field_validator("text", "source", "source_message_id", mode="before")
    @classmethod
    def strip_required_text_fields(cls, value: object) -> object:
        """Normalize surrounding whitespace before Pydantic enforces minimum lengths."""

        return value.strip() if isinstance(value, str) else value

    @field_validator("callsign", mode="before")
    @classmethod
    def normalize_optional_callsign(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_time_window(self) -> Self:
        if self.started_at is not None and self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must be greater than or equal to started_at")
        return self


class TransmissionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: UUID
    agent_id: UUID | None
    channel_id: UUID | None
    source_type: str
    source_message_id: str
    started_at: datetime | None
    ended_at: datetime | None
    received_at: datetime
    created_at: datetime


class TranscriptResponse(BaseModel):
    id: UUID
    organization_id: UUID
    transmission_id: UUID
    raw_text: str
    normalized_text: str
    language: str
    confidence: float | None
    provider: str
    model: str | None
    processing_latency_ms: int | None
    created_at: datetime


class OperationalEventResponse(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: UUID
    transmission_id: UUID
    transcript_id: UUID
    event_type: str
    summary: str
    callsign: str | None
    location_text: str | None
    latitude: float | None
    longitude: float | None
    elevation_ft: int | None
    aspect: str | None
    severity: str | None
    confidence: float
    data: dict[str, object]
    source: str
    created_at: datetime


class TransmissionIngestResponse(BaseModel):
    transmission: TransmissionResponse
    transcript: TranscriptResponse
    events: list[OperationalEventResponse]
    duplicate: bool = False


class PaginatedAgents(BaseModel):
    items: list[AgentResponse]
    limit: int
    offset: int


class PaginatedChannels(BaseModel):
    items: list[ChannelResponse]
    limit: int
    offset: int


class PaginatedCallsigns(BaseModel):
    items: list[CallsignResponse]
    limit: int
    offset: int


class PaginatedTransmissions(BaseModel):
    items: list[TransmissionResponse]
    limit: int
    offset: int


class PaginatedTranscripts(BaseModel):
    items: list[TranscriptResponse]
    limit: int
    offset: int


class PaginatedEvents(BaseModel):
    items: list[OperationalEventResponse]
    limit: int
    offset: int
