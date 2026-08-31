"""Session-protected Satchy proposal review and approval workflow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.actions.models import ActionType, SatchyAction, SatchyEvaluation
from terrasatch.actions.service import approve_action, queue_approved_action, reject_action
from terrasatch.admin.satchy_ui import render_satchy_control_plane
from terrasatch.admin.security import csrf_token_is_valid, issue_csrf_token
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.edge.models import EdgeCommand
from terrasatch.errors import TerraSatchError
from terrasatch.identity.models import Organization
from terrasatch.organizations.service import list_organizations, resolve_organization
from terrasatch.outbound.models import OutboundTransmission
from terrasatch.radio.models import RadioConversation, Transcript, Transmission

router = APIRouter(tags=["admin"])


def _require_admin(request: Request, settings: Settings) -> None:
    if not settings.admin_is_configured:
        raise HTTPException(status_code=404, detail="Admin console is not configured")
    if request.session.get("admin_authenticated") is not True:
        raise HTTPException(status_code=401, detail="Admin login required")


def _verify_csrf(request: Request, submitted: str) -> None:
    if not csrf_token_is_valid(request.session, submitted):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


async def _run_database[Result](
    settings: Settings,
    operation: Callable[[AsyncSession], Awaitable[Result]],
) -> Result:
    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        try:
            result = await operation(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


async def _workflows(
    session: AsyncSession,
    organization_id: UUID,
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            select(
                SatchyAction,
                SatchyEvaluation,
                Transmission,
                Transcript,
                RadioConversation,
                OutboundTransmission,
                EdgeCommand,
            )
            .join(
                Transmission,
                and_(
                    Transmission.id == SatchyAction.source_transmission_id,
                    Transmission.organization_id == organization_id,
                ),
            )
            .outerjoin(
                Transcript,
                and_(
                    Transcript.transmission_id == Transmission.id,
                    Transcript.organization_id == organization_id,
                ),
            )
            .join(
                RadioConversation,
                and_(
                    RadioConversation.id == SatchyAction.conversation_id,
                    RadioConversation.organization_id == organization_id,
                ),
            )
            .outerjoin(
                SatchyEvaluation,
                and_(
                    SatchyEvaluation.id == SatchyAction.evaluation_id,
                    SatchyEvaluation.organization_id == organization_id,
                ),
            )
            .outerjoin(
                OutboundTransmission,
                and_(
                    OutboundTransmission.action_id == SatchyAction.id,
                    OutboundTransmission.organization_id == organization_id,
                ),
            )
            .outerjoin(
                EdgeCommand,
                and_(
                    EdgeCommand.outbound_transmission_id == OutboundTransmission.id,
                    EdgeCommand.organization_id == organization_id,
                ),
            )
            .where(SatchyAction.organization_id == organization_id)
            .order_by(SatchyAction.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            "action": row[0],
            "evaluation": row[1],
            "transmission": row[2],
            "transcript": row[3],
            "conversation": row[4],
            "outbound": row[5],
            "command": row[6],
        }
        for row in rows
    ]


@router.get("/admin/satchy", response_class=HTMLResponse, include_in_schema=False)
async def admin_satchy_control_plane(
    request: Request,
    organization: str = "",
) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    _require_admin(request, settings)
    organizations = await _run_database(settings, list_organizations)
    selected_name = "No organization selected"
    workflows: list[dict[str, object]] = []
    selected_id = ""
    error_message = request.query_params.get("error")
    if organization:
        try:
            selected = await _run_database(
                settings, lambda session: resolve_organization(session, organization)
            )
            selected_name = selected.name
            selected_id = str(selected.id)
            workflows = await _run_database(
                settings, lambda session: _workflows(session, selected.id)
            )
        except TerraSatchError as error:
            error_message = error.message
    return HTMLResponse(
        render_satchy_control_plane(
            organizations=organizations,
            selected_organization=selected_id,
            selected_name=selected_name,
            workflows=workflows,
            csrf_token=issue_csrf_token(request.session),
            error_message=error_message,
        )
    )


async def _selected_organization(
    session: AsyncSession,
    selector: str,
) -> Organization:
    return await resolve_organization(session, selector)


@router.post("/admin/satchy/actions/{action_id}/approve", include_in_schema=False)
async def admin_approve_satchy_action(
    action_id: UUID,
    request: Request,
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    message: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_admin(request, settings)
    _verify_csrf(request, csrf_token)

    async def approve(session: AsyncSession) -> None:
        selected = await _selected_organization(session, organization)
        action, _ = await approve_action(
            session,
            organization_id=selected.id,
            action_id=action_id,
            approver_role="admin",
            notes=notes,
            edited_message=message or None,
        )
        if action.action_type == ActionType.REPLY_RADIO.value:
            await queue_approved_action(
                session,
                organization_id=selected.id,
                action_id=action.id,
            )

    try:
        await _run_database(settings, approve)
    except TerraSatchError as error:
        return RedirectResponse(
            f"/admin/satchy?organization={quote(organization)}&error={quote(error.message)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        f"/admin/satchy?organization={quote(organization)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/satchy/actions/{action_id}/reject", include_in_schema=False)
async def admin_reject_satchy_action(
    action_id: UUID,
    request: Request,
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_admin(request, settings)
    _verify_csrf(request, csrf_token)

    async def reject(session: AsyncSession) -> None:
        selected = await _selected_organization(session, organization)
        await reject_action(
            session,
            organization_id=selected.id,
            action_id=action_id,
            approver_role="admin",
            notes=notes,
        )

    try:
        await _run_database(settings, reject)
    except TerraSatchError as error:
        return RedirectResponse(
            f"/admin/satchy?organization={quote(organization)}&error={quote(error.message)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        f"/admin/satchy?organization={quote(organization)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
