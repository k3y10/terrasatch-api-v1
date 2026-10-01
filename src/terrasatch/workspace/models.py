"""Persistent, member-private Satchy conversations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
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


class WorkspacePreference(TimestampMixin, Base):
    """Personal layout only; hiding a module never deletes operational records."""

    __tablename__ = "workspace_preferences"
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    modules: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    satchy_preferences: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )


class WorkspaceProfile(TimestampMixin, Base):
    """Organization-level workspace convergence profile.

    This profile describes the shared workspace/runtime contract. Personal layout
    preferences stay in WorkspacePreference and remain independent.
    """

    __tablename__ = "workspace_profiles"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    operational_domain: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    workspace_template: Mapped[str] = mapped_column(String(100), default="general", nullable=False)
    runtime_mode: Mapped[str] = mapped_column(String(32), default="legacy", nullable=False)
    recommended_modules: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    preferred_map_layers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    workflow_preferences: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    discovery_state: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class WorkspaceDiscoveryEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only evidence observed during Satchy Discovery."""

    __tablename__ = "workspace_discovery_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "dedupe_key",
            name="uq_workspace_discovery_events_org_dedupe",
        ),
        Index(
            "ix_workspace_discovery_events_org_occurred",
            "organization_id",
            "occurred_at",
        ),
        Index(
            "ix_workspace_discovery_events_org_workflow",
            "organization_id",
            "workflow_key",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    workflow_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    workflow_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WorkspaceMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_messages"
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(128))
