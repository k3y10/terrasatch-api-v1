"""Persistent radio-domain records for the first TerraSatch intelligence pipeline."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A configured TerraSatch processing agent scoped to one organization and site."""

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_agents_org_slug"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    profile: Mapped[str] = mapped_column(String(100), default="general", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Channel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A logical monitored channel independent of the eventual RF/audio source."""

    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_channels_org_slug"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    profile: Mapped[str] = mapped_column(String(100), default="general", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Callsign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant-owned radio callsign and its known aliases."""

    __tablename__ = "callsigns"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_callsigns_org_name"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RadioConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Deterministically grouped radio activity within a tenant site and channel."""

    __tablename__ = "radio_conversations"
    __table_args__ = (
        Index(
            "ix_radio_conversations_active_lookup",
            "organization_id",
            "site_id",
            "channel_id",
            "status",
            "last_activity_at",
        ),
        Index(
            "ix_radio_conversations_participants",
            "organization_id",
            "participant_fingerprint",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    primary_topic: Mapped[str | None] = mapped_column(String(255))
    active_location: Mapped[str | None] = mapped_column(String(255))
    operational_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operational_events.id", ondelete="SET NULL"), index=True
    )
    participants: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    participant_fingerprint: Mapped[str] = mapped_column(String(512), nullable=False)


class Transmission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable source-level record representing one received or submitted transmission."""

    __tablename__ = "transmissions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_message_id",
            name="uq_transmissions_org_source_message",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    channel_id: Mapped[UUID | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"))
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("radio_conversations.id", ondelete="SET NULL"), index=True
    )
    speaker_callsign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("callsigns.id", ondelete="SET NULL"), index=True
    )
    recipient_callsign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("callsigns.id", ondelete="SET NULL"), index=True
    )
    speaker_text: Mapped[str | None] = mapped_column(String(255))
    recipient_text: Mapped[str | None] = mapped_column(String(255))
    addressed_to_agent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    addressing_confidence: Mapped[float | None] = mapped_column(Float)
    emergency_candidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    emergency_confidence: Mapped[float | None] = mapped_column(Float)
    emergency_reason: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    rf_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class Transcript(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Preserved transcript linked one-to-one with its source transmission in v1."""

    __tablename__ = "transcripts"
    __table_args__ = (UniqueConstraint("transmission_id", name="uq_transcripts_transmission_id"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transmission_id: Mapped[UUID] = mapped_column(
        ForeignKey("transmissions.id", ondelete="CASCADE"), nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    processing_latency_ms: Mapped[int | None]


class OperationalEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured interpretation that always preserves provenance back to source records."""

    __tablename__ = "operational_events"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    transmission_id: Mapped[UUID] = mapped_column(
        ForeignKey("transmissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transcript_id: Mapped[UUID] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    region_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("regions.id", ondelete="SET NULL"), index=True
    )
    terrain_cell_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("terrain_cells.id", ondelete="SET NULL"), index=True
    )
    spatial_status: Mapped[str | None] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    callsign: Mapped[str | None] = mapped_column(String(255))
    location_text: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    elevation_ft: Mapped[int | None]
    aspect: Mapped[str | None] = mapped_column(String(8))
    severity: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
