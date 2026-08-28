"""Persistence models for TerraSatch Edge pairing and registered devices."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint
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
