"""Tenant-authenticated partner integration endpoints."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from terrasatch.auth.dependencies import Principal, require_scope
from terrasatch.errors import ProviderUnavailable
from terrasatch.integrations.flaik import (
    FlaikClient,
    FlaikOperationalSnapshot,
    FlaikRadioContext,
    correlate_radio_text,
)
from terrasatch.intelligence.core import TerraEngine
from terrasatch.intelligence.providers import IntelligenceProviderError, build_intelligence_provider

router = APIRouter(prefix="/integrations", tags=["integrations"])


class FlaikCorrelationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    callsign: str | None = Field(default=None, max_length=255)


class FlaikCorrelationResponse(BaseModel):
    context: FlaikRadioContext
    engine_events: list[dict[str, object]]
    snapshot_synced_at: str


async def _snapshot(request: Request) -> FlaikOperationalSnapshot:
    try:
        return await FlaikClient(request.app.state.settings).snapshot()
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise ProviderUnavailable("flaik operational context is temporarily unavailable") from exc


@router.get("/flaik/status", response_model=FlaikOperationalSnapshot)
async def get_flaik_status(
    request: Request,
    _principal: Annotated[Principal, Depends(require_scope("read:integrations"))],
) -> FlaikOperationalSnapshot:
    """Return PII-minimized Snowbird Mountain School operational context from flaik."""

    return await _snapshot(request)


@router.post("/flaik/correlate", response_model=FlaikCorrelationResponse)
async def correlate_flaik_radio(
    payload: FlaikCorrelationRequest,
    request: Request,
    _principal: Annotated[Principal, Depends(require_scope("read:integrations"))],
) -> FlaikCorrelationResponse:
    """Correlate radio text with flaik context and run it through canonical TerraEngine."""

    snapshot = await _snapshot(request)
    context = correlate_radio_text(payload.text, snapshot)
    try:
        provider = build_intelligence_provider(request.app.state.settings)
    except IntelligenceProviderError as exc:
        raise ProviderUnavailable(str(exc)) from exc
    engine = TerraEngine(provider)
    events = await engine.process(
        text=payload.text,
        callsign_hint=payload.callsign,
        operational_context={"flaik": context.model_dump(mode="json")},
    )
    return FlaikCorrelationResponse(
        context=context,
        engine_events=[event.model_dump(mode="json") for event in events],
        snapshot_synced_at=snapshot.synced_at.isoformat(),
    )
