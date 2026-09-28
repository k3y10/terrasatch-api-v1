"""Persistent models for TerraSatch-owned questionnaires and promotions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class SurveyCampaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback_survey_campaigns"

    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class SurveySource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback_survey_sources"
    __table_args__ = (
        UniqueConstraint("campaign_id", "code", name="uq_feedback_source_campaign_code"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("feedback_survey_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SurveyResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback_survey_responses"
    __table_args__ = (
        Index("ix_feedback_response_campaign_created", "campaign_id", "created_at"),
        Index("ix_feedback_response_source_code", "source_code"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("feedback_survey_campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("feedback_survey_sources.id", ondelete="SET NULL"), nullable=True
    )
    source_code: Mapped[str] = mapped_column(String(100), default="direct", nullable=False)
    audience: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    answers: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    concept_interest: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class GiveawayCampaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback_giveaway_campaigns"

    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    official_rules_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class GiveawayEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback_giveaway_entries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "email", name="uq_feedback_giveaway_campaign_email"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("feedback_giveaway_campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    resort_preference: Mapped[str] = mapped_column(String(32), nullable=False)
    rules_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
