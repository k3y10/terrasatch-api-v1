"""Persistent Satchy evaluations, proposed actions, and approval audit records."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class ActionType(StrEnum):
    REPLY_RADIO = "reply_radio"
    ASK_CLARIFICATION = "ask_clarification"
    CREATE_OBSERVATION = "create_observation"
    UPDATE_EVENT = "update_event"
    NOTIFY_TEAM = "notify_team"
    GENERATE_REPORT = "generate_report"
    EMERGENCY_REVIEW = "emergency_review"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SatchyEvaluation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured, auditable evaluation generated from one inbound transmission."""

    __tablename__ = "satchy_evaluations"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("radio_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_transmission_id: Mapped[UUID] = mapped_column(
        ForeignKey("transmissions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    addressed_to_satchy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    interpretation: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_action: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    emergency_candidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    emergency_confidence: Mapped[float | None] = mapped_column(Float)
    emergency_reason: Mapped[str | None] = mapped_column(Text)
    operational_context: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )


class SatchyAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Operator-gated action proposed by Satchy; AI never executes it directly."""

    __tablename__ = "satchy_actions"
    __table_args__ = (
        Index(
            "ix_satchy_actions_review_queue",
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
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("radio_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_transmission_id: Mapped[UUID] = mapped_column(
        ForeignKey("transmissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operational_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operational_events.id", ondelete="SET NULL"), index=True
    )
    evaluation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("satchy_evaluations.id", ondelete="SET NULL"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="low", nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_message: Mapped[str | None] = mapped_column(Text)
    structured_payload: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ActionStatus.PROPOSED.value, nullable=False, index=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class ActionApproval(UUIDPrimaryKeyMixin, Base):
    """Immutable human/system decision audit for one proposed action."""

    __tablename__ = "action_approvals"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("satchy_actions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approver_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    approver_callsign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("callsigns.id", ondelete="SET NULL"), index=True
    )
    approver_role: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_transmission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transmissions.id", ondelete="SET NULL"), index=True
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
