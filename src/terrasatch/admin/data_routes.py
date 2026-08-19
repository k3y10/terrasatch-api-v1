"""Authenticated data-source, sync, backup, and canonical inspector routes."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.data_ui import render_data_inspector, render_data_sources
from terrasatch.admin.routes import _require_authenticated, _run_database, _verify_csrf
from terrasatch.admin.security import issue_csrf_token
from terrasatch.config import Settings
from terrasatch.errors import TerraSatchError
from terrasatch.masterdata.service import (
    create_data_source,
    enqueue_source_sync,
    inspect_data,
    list_backup_snapshots,
    list_data_sources,
    list_sync_runs,
    resolve_organization_id,
    source_record_counts,
    write_audit_log,
)
from terrasatch.organizations.service import list_organizations, resolve_organization

router = APIRouter(tags=["admin"])


@router.get("/admin/data-sources", response_class=HTMLResponse, include_in_schema=False)
async def admin_data_sources(request: Request, organization: str = "") -> HTMLResponse:
    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)

    async def load(session: AsyncSession) -> tuple[object, ...]:
        organizations = await list_organizations(session)
        if not organization:
            return organizations, "", "", [], {}, [], []
        selected = await resolve_organization(session, organization)
        sources = await list_data_sources(session, organization_id=selected.id)
        counts = await source_record_counts(session, organization_id=selected.id)
        runs = await list_sync_runs(session, organization_id=selected.id, limit=50)
        backups = await list_backup_snapshots(session, limit=20)
        return organizations, str(selected.id), selected.name, sources, counts, runs, backups

    try:
        organizations, selected, name, sources, counts, runs, backups = await _run_database(
            settings, load
        )
        error_message = request.query_params.get("error")
    except TerraSatchError as error:
        organizations = await _run_database(settings, list_organizations)
        selected, name, sources, counts, runs, backups = "", "", [], {}, [], []
        error_message = error.message
    csrf_token = request.session.get("csrf_token", "")
    if not csrf_token:
        csrf_token = issue_csrf_token(request.session)
    return HTMLResponse(
        render_data_sources(
            organizations=list(organizations),
            selected_organization=str(selected),
            selected_name=str(name),
            sources=list(sources),
            record_counts=dict(counts),
            sync_runs=list(runs),
            backups=list(backups),
            csrf_token=str(csrf_token),
            error_message=error_message,
        )
    )


@router.post("/admin/data-sources", include_in_schema=False)
async def admin_create_data_source(
    request: Request,
    organization: Annotated[str, Form()],
    name: Annotated[str, Form()],
    provider: Annotated[str, Form()],
    source_kind: Annotated[str, Form()],
    adapter_key: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    endpoint_url: Annotated[str, Form()] = "",
    credential_reference: Annotated[str, Form()] = "",
    enabled: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)
    _verify_csrf(request, csrf_token)

    async def create(session: AsyncSession) -> object:
        organization_id = await resolve_organization_id(session, organization)
        source = await create_data_source(
            session,
            organization_id=organization_id,
            name=name,
            provider=provider,
            source_kind=source_kind,
            adapter_key=adapter_key,
            endpoint_url=endpoint_url or None,
            credential_reference=credential_reference or None,
            enabled=enabled,
        )
        await write_audit_log(
            session,
            organization_id=organization_id,
            actor_type="admin_session",
            actor_id=settings.admin_email,
            action="data_source.create",
            target_type="data_source",
            target_id=str(source.id),
            request_id=getattr(request.state, "request_id", None),
            details={"provider": source.provider, "adapter": source.adapter_key},
        )
        return source

    try:
        await _run_database(settings, create)
    except TerraSatchError as error:
        return RedirectResponse(
            f"/admin/data-sources?organization={quote(organization)}&error={quote(error.message)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        f"/admin/data-sources?organization={quote(organization)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/data-sources/{source_id}/sync", include_in_schema=False)
async def admin_queue_source_sync(
    source_id: UUID,
    request: Request,
    organization: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)
    _verify_csrf(request, csrf_token)

    async def queue(session: AsyncSession) -> object:
        organization_id = await resolve_organization_id(session, organization)
        run = await enqueue_source_sync(
            session,
            organization_id=organization_id,
            source_selector=str(source_id),
            trigger="admin_ui",
        )
        await write_audit_log(
            session,
            organization_id=organization_id,
            actor_type="admin_session",
            actor_id=settings.admin_email,
            action="source_sync.queue",
            target_type="source_sync_run",
            target_id=str(run.id),
            request_id=getattr(request.state, "request_id", None),
            details={"data_source_id": str(source_id)},
        )
        return run

    try:
        await _run_database(settings, queue)
    except TerraSatchError as error:
        return RedirectResponse(
            f"/admin/data-sources?organization={quote(organization)}&error={quote(error.message)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        f"/admin/data-sources?organization={quote(organization)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/admin/data-inspector", response_class=HTMLResponse, include_in_schema=False)
async def admin_data_inspector(
    request: Request,
    organization: str = "",
    q: str = "",
) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    _require_authenticated(request, settings)

    async def load(session: AsyncSession) -> tuple[object, ...]:
        organizations = await list_organizations(session)
        if not organization:
            return organizations, "", "", []
        selected = await resolve_organization(session, organization)
        results = (
            await inspect_data(session, organization_id=selected.id, query=q, limit=25)
            if q.strip()
            else []
        )
        return organizations, str(selected.id), selected.name, results

    try:
        organizations, selected, name, results = await _run_database(settings, load)
        error_message = None
    except TerraSatchError as error:
        organizations = await _run_database(settings, list_organizations)
        selected, name, results = "", "", []
        error_message = error.message
    return HTMLResponse(
        render_data_inspector(
            organizations=list(organizations),
            selected_organization=str(selected),
            selected_name=str(name),
            query=q,
            results=list(results),
            error_message=error_message,
        )
    )
