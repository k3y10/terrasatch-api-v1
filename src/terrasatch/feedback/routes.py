"""Public check-in route plus founding-team-only aggregate analytics."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.billing.rate_limit import enforce_public_rate_limit
from terrasatch.database.session import create_session_factory
from terrasatch.feedback.schemas import SurveyResponseCreate
from terrasatch.feedback.service import (
    create_survey_response,
    feedback_export_csv,
    feedback_rows,
    feedback_summary,
)
from terrasatch.identity.access import get_user_organization_access
from terrasatch.identity.models import MembershipRole, User
from terrasatch.portal.routes import _require_user

router = APIRouter(prefix="/feedback", tags=["feedback"])
workspace_router = APIRouter(prefix="/api/v1/workspace", tags=["workspace-feedback"])


async def _public_limit(request: Request) -> None:
    await enforce_public_rate_limit(
        request.app.state.settings,
        category="feedback-response",
        identifier=request.client.host if request.client else "unknown",
        limit=30,
        window=3600,
    )


@router.post("/responses", status_code=status.HTTP_201_CREATED)
async def submit_response(payload: SurveyResponseCreate, request: Request):
    """Store one anonymous-by-default check-in response without campaign coupling."""

    await _public_limit(request)
    async with create_session_factory(request.app.state.settings)() as session:
        saved = await create_survey_response(session, payload)
        await session.commit()
    return {"response_id": str(saved.id), "accepted": True}


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
        return await feedback_summary(session)


@workspace_router.get("/organizations/{organization_id}/feedback/responses")
async def internal_responses(
    organization_id: UUID,
    request: Request,
    limit: int = Query(default=250, ge=1, le=1000),
):
    async with create_session_factory(request.app.state.settings)() as session:
        await _founding_team_access(request, session, organization_id)
        rows = await feedback_rows(session, limit=limit)
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
        body = await feedback_export_csv(session)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="terrasatch-field-feedback.csv"'},
    )
