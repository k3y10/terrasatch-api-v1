"""Persistent model for TerraSatch-owned questionnaire responses."""

from __future__ import annotations

from sqlalchemy import JSON, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class SurveyResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One anonymous-by-default native TerraSatch questionnaire response."""

    __tablename__ = "feedback_survey_responses"
    __table_args__ = (
        Index("ix_feedback_response_created_at", "created_at"),
        Index("ix_feedback_response_source_code", "source_code"),
    )

    source_code: Mapped[str] = mapped_column(String(100), default="direct", nullable=False)
    audience: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    answers: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    concept_interest: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
