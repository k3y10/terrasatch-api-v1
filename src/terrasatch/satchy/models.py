"""Persistent Satchy runs, field assets, and planned missions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class SatchyRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persistent workspace-agent run without storing hidden reasoning."""

    __tablename__ = "satchy_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            "request_id",
            name="uq_satchy_runs_request",
        ),
        Index(
            "ix_satchy_runs_user_recent",
            "organization_id",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_satchy_runs_status",
            "organization_id",
            "status",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    objective: Mapped[str | None] = mapped_column(Text)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False, index=True)
    run_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SatchyRunStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Inspectable operational activity for one Satchy run."""

    __tablename__ = "satchy_run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_satchy_run_steps_sequence"),
        Index(
            "ix_satchy_run_steps_run",
            "organization_id",
            "run_id",
            "sequence",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("satchy_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("satchy_actions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    source_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
