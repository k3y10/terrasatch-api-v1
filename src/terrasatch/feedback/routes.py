"""Public check-in routes plus founding-team-only aggregate analytics."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.billing.rate_limit import enforce_public_rate_limit
from terrasatch.database.session import create_session_factory
from terrasatch.feedback.schemas import GiveawayEntryCreate, SurveyResponseCreate
from terrasatch.feedback.service import (
    GIVEAWAY_SLUG,
    SURVEY_SLUG,
    create_giveaway_entry,
    create_survey_response,
    ensure_giveaway_campaign,
    ensure_survey_campaign,
    feedback_export_csv,
    feedback_rows,
    feedback_summary,
)
from terrasatch.identity.access import get_user_organization_access
from terrasatch.identity.models import MembershipRole, User
from terrasatch.portal.routes import _require_user

router = APIRouter(prefix="/feedback", tags=["feedback"])
workspace_router = APIRouter(prefix="/api/v1/workspace", tags=["workspace-feedback"])


async def _public_limit(request: Request, category: str, limit: int) -> None:
    await enforce_public_rate_limit(
        request.app.state.settings,
        category=category,
        identifier=request.client.host if request.client else "unknown",
        limit=limit,
        window=3600,
    )


@router.get("/campaigns/{slug}")
async def campaign(slug: str, request: Request):
    async with create_session_factory(request.app.state.settings)() as session:
        try:
            item = await ensure_survey_campaign(session, slug)
            giveaway = await ensure_giveaway_campaign(session, GIVEAWAY_SLUG)
            await session.commit()
        except LookupError as exc:
            await session.rollback()
            raise HTTPException(404, str(exc)) from exc
    return {
        "slug": item.slug,
        "title": item.title,
        "active": item.active,
        "anonymous_by_default": True,
        "question_count": 6,
        "giveaway": {
            "slug": giveaway.slug,
            "title": giveaway.title,
            "active": giveaway.active,
            "official_rules_url": giveaway.official_rules_url,
        },
    }


@router.post("/campaigns/{slug}/responses", status_code=status.HTTP_201_CREATED)
async def submit_response(slug: str, payload: SurveyResponseCreate, request: Request):
    await _public_limit(request, "feedback-response", 30)
    async with create_session_factory(request.app.state.settings)() as session:
        try:
            campaign_item = await ensure_survey_campaign(session, slug)
            saved = await create_survey_response(session, campaign_item, payload)
            await session.commit()
        except LookupError as exc:
            await session.rollback()
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            await session.rollback()
            raise HTTPException(409, str(exc)) from exc
    return {"response_id": str(saved.id), "accepted": True}


@router.get("/giveaways/{slug}")
async def giveaway(slug: str, request: Request):
    async with create_session_factory(request.app.state.settings)() as session:
        try:
            item = await ensure_giveaway_campaign(session, slug)
            await session.commit()
        except LookupError as exc:
            await session.rollback()
            raise HTTPException(404, str(exc)) from exc
    return {
        "slug": item.slug,
        "title": item.title,
        "active": item.active,
        "official_rules_url": item.official_rules_url,
        "survey_entry_required": False,
    }


@router.post("/giveaways/{slug}/entries", status_code=status.HTTP_201_CREATED)
async def giveaway_entry(slug: str, payload: GiveawayEntryCreate, request: Request):
    await _public_limit(request, "giveaway-entry", 10)
    async with create_session_factory(request.app.state.settings)() as session:
        try:
            campaign_item = await ensure_giveaway_campaign(session, slug)
            entry = await create_giveaway_entry(session, campaign_item, payload)
            await session.commit()
        except LookupError as exc:
            await session.rollback()
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            await session.rollback()
            raise HTTPException(409, str(exc)) from exc
    return {"entry_id": str(entry.id), "accepted": True}


async def _founding_team_access(
    request: Request, session: AsyncSession, organization_id: UUID
) -> tuple[User, object]:
    user_id = await _require_user(request, request.app.state.settings, session=session)
    user = await session.get(User, user_id)
    if user is None or not user.enabled:
        raise HTTPException(401, "Sign in required")
    membership = await get_user_organization_access(
        session, user_id=user.id, organization_id=organization_id
    )
    allowed = set(request.app.state.settings.feedback_internal_emails)
    if membership.role != MembershipRole.OWNER or user.email.casefold() not in allowed:
        raise HTTPException(403, "Founding-team feedback access required")
    return user, membership


@workspace_router.get("/organizations/{organization_id}/feedback/summary")
async def internal_summary(organization_id: UUID, request: Request):
    async with create_session_factory(request.app.state.settings)() as session:
        await _founding_team_access(request, session, organization_id)
        campaign_item = await ensure_survey_campaign(session, SURVEY_SLUG)
        result = await feedback_summary(session, campaign_item)
        await session.commit()
        return result


@workspace_router.get("/organizations/{organization_id}/feedback/responses")
async def internal_responses(
    organization_id: UUID,
    request: Request,
    limit: int = Query(default=250, ge=1, le=1000),
):
    async with create_session_factory(request.app.state.settings)() as session:
        await _founding_team_access(request, session, organization_id)
        campaign_item = await ensure_survey_campaign(session, SURVEY_SLUG)
        rows = await feedback_rows(session, campaign_item, limit=limit)
        await session.commit()
        return {
            "responses": [
                {
                    "id": str(row.id),
                    "created_at": row.created_at,
                    "source": row.source_code,
                    "audience": row.audience,
                    **dict(row.answers or {}),
                    "concept_interest": row.concept_interest,
                    "comment": row.comment,
                }
                for row in rows
            ]
        }


@workspace_router.get("/organizations/{organization_id}/feedback/export.csv")
async def internal_export_csv(organization_id: UUID, request: Request):
    async with create_session_factory(request.app.state.settings)() as session:
        await _founding_team_access(request, session, organization_id)
        campaign_item = await ensure_survey_campaign(session, SURVEY_SLUG)
        body = await feedback_export_csv(session, campaign_item)
        await session.commit()
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="terrasatch-field-feedback.csv"'},
    )
