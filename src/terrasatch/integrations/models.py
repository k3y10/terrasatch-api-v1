"""Tenant-scoped external integration connection records.

Connection rows deliberately contain metadata only. OAuth refresh tokens, API keys, passwords,
and other provider credentials must live in a server-side secret store and be referenced by an
opaque credential_ref written by trusted provider adapters.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class IntegrationScope(StrEnum):
    USER = "user"
    TEAM = "team"
    ORGANIZATION = "organization"


class IntegrationStatus(StrEnum):
    REQUESTED = "requested"
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    CONNECTED = "connected"
    ERROR = "error"
    DISABLED = "disabled"
    REVOKED = "revoked"


class IntegrationConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A provider connection request or active connection inside one tenant boundary."""

    __tablename__ = "integration_connections"
    __table_args__ = (
        Index(
            "ix_integration_connections_scope",
            "organization_id",
            "scope_type",
            "team_id",
            "owner_user_id",
        ),
        Index(
            "ix_integration_connections_provider_status",
            "organization_id",
            "provider",
            "status",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=IntegrationStatus.REQUESTED.value, nullable=False, index=True
    )
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    provider_account_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
