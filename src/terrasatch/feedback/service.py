"""Service layer for anonymous feedback and TerraSatch-owned attribution."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.feedback.models import FeedbackDistribution, SurveyResponse
from terrasatch.feedback.schemas import DistributionCreate, SurveyResponseCreate

FORM_ID = "OUTFIELD-CHECKIN"
FORM_VERSION = 3
FORM_TITLE = "Quick Outdoor & Field Check-In"
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


def _branch_path(payload: SurveyResponseCreate) -> list[str]:
    path = [
        f"audience:{payload.audience}",
        f"activity:{payload.activity_context}",
        f"connectivity:{payload.connectivity}",
        f"pain:{payload.primary_hassle}",
    ]
    path.extend(f"tool:{tool}" for tool in payload.tools)
    if payload.tool_follow_up:
        path.append(f"tool_follow_up:{payload.tool_follow_up}")
    if payload.pain_follow_up:
        path.append(f"pain_follow_up:{payload.pain_follow_up}")
    if payload.time_burden:
        path.append(f"time_burden:{payload.time_burden}")
    return path


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
            "activity_context": payload.activity_context,
            "tools": payload.tools,
            "primary_tool": payload.tools[0],
            "primary_hassle": payload.primary_hassle,
            "connectivity": payload.connectivity,
            "tool_follow_up": payload.tool_follow_up,
            "pain_follow_up": payload.pain_follow_up,
            "time_burden": payload.time_burden,
            "spend_band": payload.spend_band,
            "questions_shown": payload.questions_shown,
            "branch_path": _branch_path(payload),
            "started_at": payload.started_at.isoformat(),
            "completion_seconds": payload.completion_seconds,
            "contact_email": payload.contact_email,
            "contact_phone": payload.contact_phone,
            "other_details": payload.other_details,
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


def _csv_safe(value: object) -> str:
    """Keep user-provided spreadsheet cells from being interpreted as formulas."""

    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def _tool_count(rows: list[SurveyResponse]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        tools = row.answers.get("tools") or []
        if isinstance(tools, list):
            counter.update(str(tool) for tool in tools)
    return dict(counter)


async def feedback_summary(session: AsyncSession) -> dict[str, object]:
    rows = await feedback_rows(session, limit=100_000)
    distributions = await list_distributions(session)
    counts = Counter(row.distribution_id for row in rows)
    return {
        "form": {
            "id": FORM_ID,
            "version": FORM_VERSION,
            "title": FORM_TITLE,
            "adaptive": True,
        },
        "responses": len(rows),
        "audience": _count(rows, lambda row: row.audience),
        "activity_context": _count(
            rows, lambda row: row.answers.get("activity_context", "unknown")
        ),
        "tools": _tool_count(rows),
        "primary_hassle": _count(
            rows, lambda row: row.answers.get("primary_hassle", "unknown")
        ),
        "connectivity": _count(
            rows, lambda row: row.answers.get("connectivity", "unknown")
        ),
        "time_burden": _count(
            rows, lambda row: row.answers.get("time_burden") or "not_asked"
        ),
        "spend_band": _count(
            rows, lambda row: row.answers.get("spend_band", "unknown")
        ),
        "concept_interest": _count(rows, lambda row: row.concept_interest),
        "contactable_responses": sum(
            1
            for row in rows
            if row.answers.get("contact_email") or row.answers.get("contact_phone")
        ),
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
            "activity_context",
            "tools",
            "primary_hassle",
            "connectivity",
            "tool_follow_up",
            "pain_follow_up",
            "time_burden",
            "spend_band",
            "concept_interest",
            "completion_seconds",
            "contact_email",
            "contact_phone",
            "other_details",
            "questions_shown",
            "branch_path",
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
                row.answers.get("activity_context", ""),
                "|".join(str(item) for item in (row.answers.get("tools") or [])),
                row.answers.get("primary_hassle", ""),
                row.answers.get("connectivity", ""),
                row.answers.get("tool_follow_up", ""),
                row.answers.get("pain_follow_up", ""),
                row.answers.get("time_burden", ""),
                row.answers.get("spend_band", ""),
                row.concept_interest,
                row.answers.get("completion_seconds", ""),
                _csv_safe(row.answers.get("contact_email", "")),
                _csv_safe(row.answers.get("contact_phone", "")),
                _csv_safe(
                    json.dumps(
                        row.answers.get("other_details", {}),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                ),
                "|".join(
                    str(item) for item in (row.answers.get("questions_shown") or [])
                ),
                "|".join(str(item) for item in (row.answers.get("branch_path") or [])),
                _csv_safe(row.comment or ""),
            ]
        )
    return output.getvalue()
