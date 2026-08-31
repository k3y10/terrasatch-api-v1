"""Structured organization/site context used by Satchy evaluation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class OrganizationOperationalProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Lightweight operational vocabulary without a document/vector dependency."""

    __tablename__ = "organization_operational_profiles"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "site_id",
            name="uq_operational_profiles_org_site",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), index=True
    )
    industry: Mapped[str | None] = mapped_column(String(100))
    operation_type: Mapped[str | None] = mapped_column(String(100))
    teams: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    roles: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    callsigns: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    radio_protocol: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    terminology: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    location_aliases: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    emergency_terms: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
