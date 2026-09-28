"""Service layer for anonymous feedback and separate giveaway identity data."""

from __future__ import annotations

import csv
import io
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.feedback.models import (
    GiveawayCampaign,
    GiveawayEntry,
    SurveyCampaign,
    SurveyResponse,
    SurveySource,
)
from terrasatch.feedback.schemas import GiveawayEntryCreate, SurveyResponseCreate

SURVEY_SLUG = "outdoor-field-check-in-fall-2026"
SURVEY_TITLE = "60-Second Outdoor & Field Check-In"
GIVEAWAY_SLUG = "ski-day-2026-27"
GIVEAWAY_TITLE = "TerraSatch Free Ski Day Giveaway"


async def ensure_survey_campaign(session: AsyncSession, slug: str) -> SurveyCampaign:
    if slug != SURVEY_SLUG:
        raise LookupError("Unknown survey campaign")
    campaign = await session.scalar(select(SurveyCampaign).where(SurveyCampaign.slug == slug))
    if campaign is None:
        campaign = SurveyCampaign(
            slug=SURVEY_SLUG,
            title=SURVEY_TITLE,
            active=True,
            configuration={"anonymous_by_default": True, "question_count": 6},
        )
        session.add(campaign)
        await session.flush()
    return campaign


async def ensure_giveaway_campaign(session: AsyncSession, slug: str) -> GiveawayCampaign:
    if slug != GIVEAWAY_SLUG:
        raise LookupError("Unknown giveaway campaign")
    campaign = await session.scalar(select(GiveawayCampaign).where(GiveawayCampaign.slug == slug))
    if campaign is None:
        campaign = GiveawayCampaign(
            slug=GIVEAWAY_SLUG,
            title=GIVEAWAY_TITLE,
            active=False,
            official_rules_url=None,
            configuration={
                "survey_entry_required": False,
                "survey_completion_changes_odds": False,
                "resorts_are_sponsors": False,
            },
        )
        session.add(campaign)
        await session.flush()
    return campaign


async def create_survey_response(
    session: AsyncSession, campaign: SurveyCampaign, payload: SurveyResponseCreate
) -> SurveyResponse:
    if not campaign.active:
        raise PermissionError("Survey campaign is not accepting responses")
    source = await session.scalar(
        select(SurveySource).where(
            SurveySource.campaign_id == campaign.id,
            SurveySource.code == payload.source_code,
            SurveySource.enabled.is_(True),
        )
    )
    response = SurveyResponse(
        campaign_id=campaign.id,
        source_id=source.id if source else None,
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


async def feedback_rows(session: AsyncSession, campaign: SurveyCampaign, limit: int = 1000):
    return list(
        await session.scalars(
            select(SurveyResponse)
            .where(SurveyResponse.campaign_id == campaign.id)
            .order_by(SurveyResponse.created_at.desc())
            .limit(limit)
        )
    )


def _count(rows, key):
    return dict(Counter(key(row) for row in rows))


async def feedback_summary(session: AsyncSession, campaign: SurveyCampaign) -> dict[str, object]:
    rows = await feedback_rows(session, campaign, limit=100_000)
    return {
        "campaign": {"slug": campaign.slug, "title": campaign.title},
        "responses": len(rows),
        "audience": _count(rows, lambda row: row.audience),
        "primary_hassle": _count(rows, lambda row: row.answers.get("primary_hassle", "unknown")),
        "connectivity": _count(rows, lambda row: row.answers.get("connectivity", "unknown")),
        "spend_band": _count(rows, lambda row: row.answers.get("spend_band", "unknown")),
        "concept_interest": _count(rows, lambda row: row.concept_interest),
        "source": _count(rows, lambda row: row.source_code),
    }


async def feedback_export_csv(session: AsyncSession, campaign: SurveyCampaign) -> str:
    rows = await feedback_rows(session, campaign, limit=100_000)
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


async def create_giveaway_entry(
    session: AsyncSession, campaign: GiveawayCampaign, payload: GiveawayEntryCreate
) -> GiveawayEntry:
    if not campaign.active or not campaign.official_rules_url:
        raise PermissionError("Giveaway entry is not open yet")
    existing = await session.scalar(
        select(GiveawayEntry).where(
            GiveawayEntry.campaign_id == campaign.id,
            GiveawayEntry.email == payload.email,
        )
    )
    if existing is not None:
        return existing
    entry = GiveawayEntry(
        campaign_id=campaign.id,
        name=payload.name,
        email=payload.email,
        resort_preference=payload.resort_preference,
        rules_accepted=payload.rules_accepted,
    )
    session.add(entry)
    await session.flush()
    return entry
