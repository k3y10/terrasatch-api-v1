"""Persistence models for TerraSatch Edge pairing and registered devices."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class EdgePairing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "edge_pairings"

    device_code_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    user_code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    requested_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255))
    platform: Mapped[str | None] = mapped_column(String(100))
    architecture: Mapped[str | None] = mapped_column(String(100))
    agent_version: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    site_id: Mapped[UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"))
    approved_by_api_key_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL")
    )


class EdgeDevice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "edge_devices"
    __table_args__ = (UniqueConstraint("api_key_id", name="uq_edge_devices_api_key"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    api_key_id: Mapped[UUID] = mapped_column(
        ForeignKey("api_keys.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255))
    platform: Mapped[str | None] = mapped_column(String(100))
    architecture: Mapped[str | None] = mapped_column(String(100))
    agent_version: Mapped[str | None] = mapped_column(String(64))
    hardware_inventory: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    remote_config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    telemetry: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EdgeCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Reusable API-to-Edge command envelope with strict device/site ownership."""

    __tablename__ = "edge_commands"
    __table_args__ = (
        Index(
            "ix_edge_commands_device_queue",
            "organization_id",
            "site_id",
            "edge_device_id",
            "status",
            "priority",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    edge_device_id: Mapped[UUID] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outbound_transmission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("outbound_transmissions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    command_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    priority: Mapped[int] = mapped_column(default=100, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
