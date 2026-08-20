"""Tenant-authenticated partner integration endpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.auth.dependencies import Principal, require_scope
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable, ResourceNotFound
from terrasatch.integrations.flaik import (
    FlaikClient,
    FlaikOperationalSnapshot,
    FlaikRadioContext,
    correlate_radio_text,
)
from terrasatch.intelligence.core import TerraEngine
from terrasatch.intelligence.providers import IntelligenceProviderError, build_intelligence_provider
from terrasatch.masterdata.partner_sources import resolve_partner_source

router = APIRouter(prefix="/integrations", tags=["integrations"])


class FlaikCorrelationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    callsign: str | None = Field(default=None, max_length=255)
    site_id: UUID | None = None


class FlaikCorrelationResponse(BaseModel):
    context: FlaikRadioContext
    engine_events: list[dict[str, object]]
    snapshot_synced_at: str


async def _run_database[Result](
    settings: Settings,
    operation: Callable[[AsyncSession], Awaitable[Result]],
) -> Result:
    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        return await operation(session)


async def _snapshot(
    request: Request,
    *,
    organization_id: UUID,
    site_id: UUID | None,
) -> FlaikOperationalSnapshot:
    try:
        source = await _run_database(
            request.app.state.settings,
            lambda session: resolve_partner_source(
                session,
                organization_id=organization_id,
                provider="flaik",
                site_id=site_id,
            ),
        )
        return await FlaikClient(source).snapshot()
    except (httpx.HTTPError, InvalidConfiguration, ResourceNotFound, ValueError) as exc:
        raise ProviderUnavailable(
            "flaik operational context is temporarily unavailable"
        ) from exc


@router.get("/flaik/status", response_model=FlaikOperationalSnapshot)
async def get_flaik_status(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:integrations"))],
    site_id: Annotated[UUID | None, Query()] = None,
) -> FlaikOperationalSnapshot:
    """Return only the authenticated organization's site-scoped flaik context."""

    return await _snapshot(
        request,
        organization_id=principal.organization_id,
        site_id=site_id,
    )


@router.post("/flaik/correlate", response_model=FlaikCorrelationResponse)
async def correlate_flaik_radio(
    payload: FlaikCorrelationRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:integrations"))],
) -> FlaikCorrelationResponse:
    """Correlate radio text without creating a Snowbird-only event architecture."""

    snapshot = await _snapshot(
        request,
        organization_id=principal.organization_id,
        site_id=payload.site_id,
    )
    context = correlate_radio_text(payload.text, snapshot)
    try:
        provider = build_intelligence_provider(request.app.state.settings)
    except IntelligenceProviderError as exc:
        raise ProviderUnavailable(str(exc)) from exc
    events = await TerraEngine(provider).process(
        text=payload.text,
        callsign_hint=payload.callsign,
        operational_context={"flaik": context.model_dump(mode="json")},
    )
    return FlaikCorrelationResponse(
        context=context,
        engine_events=[event.model_dump(mode="json") for event in events],
        snapshot_synced_at=snapshot.synced_at.isoformat(),
    )
