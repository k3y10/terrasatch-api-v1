"""Persistent field assets and Satchy-planned missions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class FieldAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_assets"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_field_assets_org_name"),
        Index("ix_field_assets_scope", "organization_id", "site_id", "team_id", "owner_user_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL"), index=True
    )
    team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    controller_edge_device_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="offline", nullable=False, index=True)
    location: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    policy: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FieldMission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_missions"
    __table_args__ = (
        Index("ix_field_missions_queue", "organization_id", "site_id", "status", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("field_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    requested_by_callsign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("callsigns.id", ondelete="SET NULL"), index=True
    )
    source_transmission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transmissions.id", ondelete="SET NULL"), index=True
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("radio_conversations.id", ondelete="SET NULL"), index=True
    )
    action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("satchy_actions.id", ondelete="SET NULL"), unique=True, index=True
    )
    edge_command_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("edge_commands.id", ondelete="SET NULL"), unique=True, index=True
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    mission_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    required_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    target: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="moderate", nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="proposed", nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
