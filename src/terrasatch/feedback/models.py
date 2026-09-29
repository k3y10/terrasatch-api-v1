"""Persistent models for TerraSatch-owned questionnaire responses and distribution metadata."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class FeedbackDistribution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """TerraSatch-owned first-party attribution metadata for a link or QR placement."""

    __tablename__ = "feedback_distributions"

    distribution_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    placement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audience_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SurveyResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One anonymous-by-default native TerraSatch questionnaire response."""

    __tablename__ = "feedback_survey_responses"
    __table_args__ = (
        Index("ix_feedback_response_form_version", "form_id", "form_version"),
        Index("ix_feedback_response_created_at", "created_at"),
        Index("ix_feedback_response_distribution_id", "distribution_id"),
    )

    form_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    form_version: Mapped[int] = mapped_column(Integer, nullable=False)
    distribution_id: Mapped[str] = mapped_column(String(100), nullable=False)
    audience: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    answers: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    concept_interest: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
