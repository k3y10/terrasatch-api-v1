"""Outbound transmission records kept separate from immutable inbound RF traffic."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class OutboundStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    EDGE_RECEIVED = "edge_received"
    WAITING_CHANNEL_CLEAR = "waiting_channel_clear"
    SIMULATED = "simulated"
    TRANSMITTING = "transmitting"
    TRANSMITTED = "transmitted"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OutboundTransmission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Approved outbound intent; never shares the inbound Transmission lifecycle."""

    __tablename__ = "outbound_transmissions"
    __table_args__ = (
        Index(
            "ix_outbound_transmissions_device_queue",
            "edge_device_id",
            "status",
            "queued_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    edge_device_id: Mapped[UUID] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("satchy_actions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("radio_conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True
    )
    speaker_callsign: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_callsign: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    reply_route: Mapped[str] = mapped_column(String(32), default="simulation", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=OutboundStatus.DRAFT.value, nullable=False, index=True
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edge_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transmitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
