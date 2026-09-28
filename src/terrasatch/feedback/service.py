"""Service layer for anonymous feedback and TerraSatch-owned attribution."""

from __future__ import annotations

import csv
import io
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.feedback.models import FeedbackDistribution, SurveyResponse
from terrasatch.feedback.schemas import DistributionCreate, SurveyResponseCreate

FORM_ID = "OUTFIELD-CHECKIN"
FORM_VERSION = 1
FORM_TITLE = "60-Second Outdoor & Field Check-In"
DIRECT_DISTRIBUTION_ID = "DIRECT"


async def resolve_distribution_id(
    session: AsyncSession, requested_id: str
) -> str:
    """Accept only TerraSatch-registered distribution IDs; otherwise use DIRECT."""

    if requested_id == DIRECT_DISTRIBUTION_ID:
        return DIRECT_DISTRIBUTION_ID
    distribution = await session.scalar(
        select(FeedbackDistribution).where(
            FeedbackDistribution.distribution_id == requested_id,
            FeedbackDistribution.enabled.is_(True),
        )
    )
    return distribution.distribution_id if distribution is not None else DIRECT_DISTRIBUTION_ID


async def create_distribution(
    session: AsyncSession, payload: DistributionCreate
) -> FeedbackDistribution:
    existing = await session.scalar(
        select(FeedbackDistribution).where(
            FeedbackDistribution.distribution_id == payload.distribution_id
        )
    )
    if existing is not None:
        raise ValueError("Distribution ID already exists")
    distribution = FeedbackDistribution(
        distribution_id=payload.distribution_id,
        label=payload.label,
        channel=payload.channel,
        placement=payload.placement,
        audience_hint=payload.audience_hint,
        metadata_json=payload.metadata,
        enabled=True,
    )
    session.add(distribution)
    await session.flush()
    return distribution


async def list_distributions(session: AsyncSession) -> list[FeedbackDistribution]:
    return list(
        await session.scalars(
            select(FeedbackDistribution).order_by(FeedbackDistribution.created_at.asc())
        )
    )


async def create_survey_response(
    session: AsyncSession, payload: SurveyResponseCreate
) -> SurveyResponse:
    distribution_id = await resolve_distribution_id(session, payload.distribution_id)
    response = SurveyResponse(
        form_id=FORM_ID,
        form_version=FORM_VERSION,
        distribution_id=distribution_id,
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


async def feedback_rows(
    session: AsyncSession,
    *,
    limit: int = 1000,
    distribution_id: str | None = None,
    audience: str | None = None,
    form_version: int | None = None,
) -> list[SurveyResponse]:
    statement = select(SurveyResponse).where(SurveyResponse.form_id == FORM_ID)
    if distribution_id:
        statement = statement.where(
            SurveyResponse.distribution_id == distribution_id.strip().upper()
        )
    if audience:
        statement = statement.where(SurveyResponse.audience == audience)
    if form_version is not None:
        statement = statement.where(SurveyResponse.form_version == form_version)
    statement = statement.order_by(SurveyResponse.created_at.desc()).limit(limit)
    return list(await session.scalars(statement))


def _count(rows, key):
    return dict(Counter(key(row) for row in rows))


async def feedback_summary(session: AsyncSession) -> dict[str, object]:
    rows = await feedback_rows(session, limit=100_000)
    distributions = await list_distributions(session)
    counts = Counter(row.distribution_id for row in rows)
    return {
        "form": {
            "id": FORM_ID,
            "version": FORM_VERSION,
            "title": FORM_TITLE,
        },
        "responses": len(rows),
        "audience": _count(rows, lambda row: row.audience),
        "primary_hassle": _count(
            rows, lambda row: row.answers.get("primary_hassle", "unknown")
        ),
        "connectivity": _count(
            rows, lambda row: row.answers.get("connectivity", "unknown")
        ),
        "spend_band": _count(
            rows, lambda row: row.answers.get("spend_band", "unknown")
        ),
        "concept_interest": _count(rows, lambda row: row.concept_interest),
        "distribution": dict(counts),
        "distribution_catalog": [
            {
                "distribution_id": DIRECT_DISTRIBUTION_ID,
                "label": "Direct / unattributed",
                "channel": "direct",
                "placement": None,
                "audience_hint": None,
                "enabled": True,
                "responses": counts.get(DIRECT_DISTRIBUTION_ID, 0),
            },
            *[
                {
                    "distribution_id": item.distribution_id,
                    "label": item.label,
                    "channel": item.channel,
                    "placement": item.placement,
                    "audience_hint": item.audience_hint,
                    "enabled": item.enabled,
                    "responses": counts.get(item.distribution_id, 0),
                }
                for item in distributions
            ],
        ],
    }


async def feedback_export_csv(
    session: AsyncSession,
    *,
    distribution_id: str | None = None,
    audience: str | None = None,
    form_version: int | None = None,
) -> str:
    rows = await feedback_rows(
        session,
        limit=100_000,
        distribution_id=distribution_id,
        audience=audience,
        form_version=form_version,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "response_id",
            "created_at",
            "form_id",
            "form_version",
            "distribution_id",
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
                row.form_id,
                row.form_version,
                row.distribution_id,
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
