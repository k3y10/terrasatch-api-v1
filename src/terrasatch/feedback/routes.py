"""Public check-in plus founding-team first-party feedback analytics."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.billing.rate_limit import enforce_public_rate_limit
from terrasatch.database.session import create_session_factory
from terrasatch.feedback.schemas import DistributionCreate, SurveyResponseCreate
from terrasatch.feedback.service import (
    FORM_ID,
    FORM_TITLE,
    FORM_VERSION,
    create_distribution,
    create_survey_response,
    feedback_export_csv,
    feedback_rows,
    feedback_summary,
    list_distributions,
)
from terrasatch.identity.access import get_user_organization_access
from terrasatch.identity.models import MembershipRole, User
from terrasatch.portal.routes import _require_user, _verify_csrf

router = APIRouter(prefix="/feedback", tags=["feedback"])
workspace_router = APIRouter(prefix="/api/v1/workspace", tags=["workspace-feedback"])

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TURNSTILE_TEST_SECRET = "1x0000000000000000000000000000000AA"


async def _verify_turnstile(request: Request, token: str) -> None:
    settings = request.app.state.settings
    configured = settings.feedback_turnstile_secret_key
    if configured is not None:
        secret = configured.get_secret_value()
    elif not settings.is_production:
        secret = _TURNSTILE_TEST_SECRET
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Human verification is not configured.",
        )

    payload = {
        "secret": secret,
        "response": token,
    }
    if request.client and request.client.host:
        payload["remoteip"] = request.client.host

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(_TURNSTILE_VERIFY_URL, data=payload)
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Human verification is temporarily unavailable.",
        ) from error

    if result.get("success") is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Human verification failed. Please try again.",
        )


async def _public_limit(request: Request) -> None:
    await enforce_public_rate_limit(
        request.app.state.settings,
        category="feedback-response",
        identifier=request.client.host if request.client else "unknown",
        limit=30,
        window=3600,
    )


@router.get("/forms/{form_id}")
async def form_metadata(form_id: str):
    """Return public metadata for the implemented native form."""

    if form_id.upper() != FORM_ID:
        raise HTTPException(404, "Unknown feedback form")
    return {
        "form_id": FORM_ID,
        "form_version": FORM_VERSION,
        "title": FORM_TITLE,
        "anonymous_by_default": True,
        "adaptive": True,
        "estimated_seconds": 60,
        "advertising_trackers": False,
    }


@router.post(
    "/forms/{form_id}/responses",
    status_code=status.HTTP_201_CREATED,
)
async def submit_response(
    form_id: str,
    payload: SurveyResponseCreate,
    request: Request,
):
    """Store a response stamped with a server-controlled form ID and version."""

    if form_id.upper() != FORM_ID:
        raise HTTPException(404, "Unknown feedback form")
    await _public_limit(request)
    await _verify_turnstile(request, payload.turnstile_token)
    async with create_session_factory(request.app.state.settings)() as session:
        saved = await create_survey_response(session, payload)
        await session.commit()
    return {
        "response_id": str(saved.id),
        "form_id": saved.form_id,
        "form_version": saved.form_version,
        "distribution_id": saved.distribution_id,
        "accepted": True,
    }


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
        result = await feedback_summary(session)
        await session.commit()
        return result


@workspace_router.get("/organizations/{organization_id}/feedback/responses")
async def internal_responses(
    organization_id: UUID,
    request: Request,
    limit: int = Query(default=250, ge=1, le=1000),
    distribution_id: str | None = Query(default=None, max_length=100),
    audience: Literal["recreation", "work", "both"] | None = None,
    form_version: int | None = Query(default=None, ge=1),
):
    async with create_session_factory(request.app.state.settings)() as session:
        await _founding_team_access(request, session, organization_id)
        rows = await feedback_rows(
            session,
            limit=limit,
            distribution_id=distribution_id,
            audience=audience,
            form_version=form_version,
        )
        return {
            "responses": [
                {
                    "id": str(row.id),
                    "created_at": row.created_at,
                    "form_id": row.form_id,
                    "form_version": row.form_version,
                    "distribution_id": row.distribution_id,
                    "audience": row.audience,
                    **dict(row.answers or {}),
                    "concept_interest": row.concept_interest,
                    "comment": row.comment,
                }
                for row in rows
            ]
        }


@workspace_router.get("/organizations/{organization_id}/feedback/distributions")
async def internal_distributions(organization_id: UUID, request: Request):
    async with create_session_factory(request.app.state.settings)() as session:
        await _founding_team_access(request, session, organization_id)
        items = await list_distributions(session)
        await session.commit()
        return {
            "form_id": FORM_ID,
            "form_version": FORM_VERSION,
            "distributions": [
                {
                    "distribution_id": "DIRECT",
                    "label": "Direct / unattributed",
                    "channel": "direct",
                    "placement": None,
                    "audience_hint": None,
                    "metadata": {},
                    "enabled": True,
                    "path": "/check-in",
                },
                *[
                    {
                        "distribution_id": item.distribution_id,
                        "label": item.label,
                        "channel": item.channel,
                        "placement": item.placement,
                        "audience_hint": item.audience_hint,
                        "metadata": item.metadata_json,
                        "enabled": item.enabled,
                        "path": f"/check-in?d={item.distribution_id}",
                    }
                    for item in items
                ],
            ],
        }


@workspace_router.post(
    "/organizations/{organization_id}/feedback/distributions",
    status_code=status.HTTP_201_CREATED,
)
async def internal_create_distribution(
    organization_id: UUID,
    payload: DistributionCreate,
    request: Request,
):
    _verify_csrf(request, request.headers.get("X-CSRF-Token", ""))
    async with create_session_factory(request.app.state.settings)() as session:
        await _founding_team_access(request, session, organization_id)
        try:
            item = await create_distribution(session, payload)
            await session.commit()
        except ValueError as exc:
            await session.rollback()
            raise HTTPException(409, str(exc)) from exc
    return {
        "distribution_id": item.distribution_id,
        "label": item.label,
        "channel": item.channel,
        "placement": item.placement,
        "audience_hint": item.audience_hint,
        "metadata": item.metadata_json,
        "enabled": item.enabled,
        "path": f"/check-in?d={item.distribution_id}",
    }


@workspace_router.get("/organizations/{organization_id}/feedback/export.csv")
async def internal_export_csv(
    organization_id: UUID,
    request: Request,
    distribution_id: str | None = Query(default=None, max_length=100),
    audience: Literal["recreation", "work", "both"] | None = None,
    form_version: int | None = Query(default=None, ge=1),
):
    async with create_session_factory(request.app.state.settings)() as session:
        await _founding_team_access(request, session, organization_id)
        body = await feedback_export_csv(
            session,
            distribution_id=distribution_id,
            audience=audience,
            form_version=form_version,
        )
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="terrasatch-field-feedback.csv"'
        },
    )
