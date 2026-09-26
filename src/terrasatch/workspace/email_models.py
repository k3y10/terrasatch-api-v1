"""Persistent TerraSatch inbound/outbound workspace email records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class WorkspaceEmailMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A provider-backed email visible in the internal TerraSatch workspace."""

    __tablename__ = "workspace_email_messages"
    __table_args__ = (
        UniqueConstraint("provider_email_id", name="uq_workspace_email_provider_id"),
        Index("ix_workspace_email_received_for", "received_for"),
        Index("ix_workspace_email_received_at", "received_at"),
        Index("ix_workspace_email_parent_id", "parent_email_id"),
    )

    provider_email_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(16), default="inbound", nullable=False)
    parent_email_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workspace_email_messages.id", ondelete="SET NULL")
    )
    recipient_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    internet_message_id: Mapped[str | None] = mapped_column(String(1024))
    received_for: Mapped[str] = mapped_column(String(320), nullable=False)
    from_address: Mapped[str] = mapped_column(String(1000), nullable=False)
    to_addresses: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cc_addresses: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    bcc_addresses: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    reply_to: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    subject: Mapped[str] = mapped_column(Text, default="", nullable=False)
    text_body: Mapped[str | None] = mapped_column(Text)
    html_body: Mapped[str | None] = mapped_column(Text)
    headers: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    attachments: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkspaceEmailRead(Base):
    """Per-user read state for a workspace email."""

    __tablename__ = "workspace_email_reads"

    email_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspace_email_messages.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
