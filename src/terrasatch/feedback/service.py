"""Service layer for anonymous TerraSatch feedback."""

from __future__ import annotations

import csv
import io
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.feedback.models import SurveyResponse
from terrasatch.feedback.schemas import SurveyResponseCreate

SURVEY_TITLE = "60-Second Outdoor & Field Check-In"


async def create_survey_response(
    session: AsyncSession, payload: SurveyResponseCreate
) -> SurveyResponse:
    response = SurveyResponse(
        source_code=payload.source_code,
        audience=payload.audience,
        answers={
            "primary_tool": payload.primary_tool,
            "primary_hassle": payload.primary_hassle,
            "connectivity": payload.connectivity,
            "spend_band": payload.spend_band,
        },
        concept_interest=payload.concept_interest,
        comment=payload.comment,
    )
    session.add(response)
    await session.flush()
    return response


async def feedback_rows(session: AsyncSession, limit: int = 1000):
    return list(
        await session.scalars(
            select(SurveyResponse)
            .order_by(SurveyResponse.created_at.desc())
            .limit(limit)
        )
    )


def _count(rows, key):
    return dict(Counter(key(row) for row in rows))


async def feedback_summary(session: AsyncSession) -> dict[str, object]:
    rows = await feedback_rows(session, limit=100_000)
    return {
        "survey": {"title": SURVEY_TITLE},
        "responses": len(rows),
        "audience": _count(rows, lambda row: row.audience),
        "primary_hassle": _count(rows, lambda row: row.answers.get("primary_hassle", "unknown")),
        "connectivity": _count(rows, lambda row: row.answers.get("connectivity", "unknown")),
        "spend_band": _count(rows, lambda row: row.answers.get("spend_band", "unknown")),
        "concept_interest": _count(rows, lambda row: row.concept_interest),
        "source": _count(rows, lambda row: row.source_code),
    }


async def feedback_export_csv(session: AsyncSession) -> str:
    rows = await feedback_rows(session, limit=100_000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "response_id",
            "created_at",
            "source",
            "audience",
            "primary_tool",
            "primary_hassle",
            "connectivity",
            "spend_band",
            "concept_interest",
            "comment",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                str(row.id),
                row.created_at.isoformat() if row.created_at else "",
                row.source_code,
                row.audience,
                row.answers.get("primary_tool", ""),
                row.answers.get("primary_hassle", ""),
                row.answers.get("connectivity", ""),
                row.answers.get("spend_band", ""),
                row.concept_interest,
                row.comment or "",
            ]
        )
    return output.getvalue()
