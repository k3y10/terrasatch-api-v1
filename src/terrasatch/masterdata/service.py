"""Tenant-safe services for source control, sync tracking, audit, and inspection."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.errors import InvalidConfiguration, ResourceConflict, ResourceNotFound
from terrasatch.identity.models import Organization
from terrasatch.masterdata.adapters import AdapterRegistry, adapters
from terrasatch.masterdata.models import (
    AuditLog,
    BackupSnapshot,
    DataSource,
    Observation,
    Region,
    SourceConnection,
    SourceRecord,
    SourceSyncRun,
    TerrainCell,
)
from terrasatch.organizations.service import slugify
from terrasatch.radio.models import OperationalEvent, Transcript, Transmission

_SECRET_MARKERS = ("api_key", "password", "secret", "token", "private_key")


@dataclass(frozen=True, slots=True)
class InspectorResult:
    """Bounded, presentation-neutral search result for the admin inspector."""

    record_type: str
    record_id: UUID
    title: str
    subtitle: str
    provenance: str = ""
    spatial: str = ""
    details: dict[str, object] = field(default_factory=dict)


async def resolve_organization_id(session: AsyncSession, selector: str) -> UUID:
    """Resolve an organization UUID or slug without crossing tenant boundaries."""

    try:
        organization_id = UUID(selector)
    except ValueError:
        organization = await session.scalar(
            select(Organization).where(Organization.slug == selector)
        )
    else:
        organization = await session.scalar(
            select(Organization).where(Organization.id == organization_id)
        )
    if organization is None:
        raise ResourceNotFound("Organization was not found")
    return organization.id


def _ensure_secretless(configuration: dict[str, object]) -> None:
    unsafe = sorted(
        key for key in configuration if any(marker in key.casefold() for marker in _SECRET_MARKERS)
    )
    if unsafe:
        raise InvalidConfiguration(
            "Source configuration must contain secret references, not raw credentials",
            details={"unsafe_keys": unsafe},
        )


async def create_data_source(
    session: AsyncSession,
    *,
    organization_id: UUID,
    name: str,
    provider: str,
    source_kind: str,
    adapter_key: str,
    endpoint_url: str | None = None,
    credential_reference: str | None = None,
    configuration: dict[str, object] | None = None,
    enabled: bool = False,
    registry: AdapterRegistry = adapters,
) -> DataSource:
    """Create one disabled-by-default provider and its secretless connection state."""

    normalized_name = name.strip()
    normalized_provider = provider.strip()
    normalized_kind = source_kind.strip().lower()
    normalized_adapter = adapter_key.strip().lower()
    if not all((normalized_name, normalized_provider, normalized_kind, normalized_adapter)):
        raise InvalidConfiguration("Name, provider, source kind, and adapter are required")
    try:
        adapter = registry.get(normalized_adapter)
    except KeyError as exc:
        raise InvalidConfiguration(str(exc)) from exc
    clean_configuration = dict(configuration or {})
    _ensure_secretless(clean_configuration)
    normalized_credential_reference = (
        credential_reference.strip() if credential_reference else None
    )
    if normalized_credential_reference and "://" not in normalized_credential_reference:
        raise InvalidConfiguration(
            "Credential reference must identify a secret manager or environment reference"
        )
    source_slug = slugify(normalized_name)
    existing = await session.scalar(
        select(DataSource).where(
            DataSource.organization_id == organization_id,
            DataSource.slug == source_slug,
        )
    )
    if existing is not None:
        raise ResourceConflict(f"Data source '{normalized_name}' already exists")

    source = DataSource(
        organization_id=organization_id,
        name=normalized_name,
        slug=source_slug,
        provider=normalized_provider,
        source_kind=normalized_kind,
        adapter_key=normalized_adapter,
        adapter_version=adapter.version,
        normalization_version="1",
        configuration=clean_configuration,
        enabled=enabled,
        status="ready" if enabled else "disabled",
    )
    session.add(source)
    await session.flush()
    session.add(
        SourceConnection(
            organization_id=organization_id,
            data_source_id=source.id,
            endpoint_url=endpoint_url.strip() if endpoint_url else None,
            credential_reference=normalized_credential_reference,
            state={},
        )
    )
    await session.flush()
    return source


async def list_data_sources(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> list[DataSource]:
    return list(
        await session.scalars(
            select(DataSource)
            .where(DataSource.organization_id == organization_id)
            .order_by(DataSource.name)
        )
    )


async def resolve_data_source(
    session: AsyncSession,
    *,
    organization_id: UUID,
    selector: str,
) -> DataSource:
    try:
        source_id = UUID(selector)
    except ValueError:
        source = await session.scalar(
            select(DataSource).where(
                DataSource.organization_id == organization_id,
                or_(
                    DataSource.slug == selector,
                    DataSource.provider == selector,
                    DataSource.name == selector,
                ),
            )
        )
    else:
        source = await session.scalar(
            select(DataSource).where(
                DataSource.organization_id == organization_id,
                DataSource.id == source_id,
            )
        )
    if source is None:
        raise ResourceNotFound("Data source was not found")
    return source


async def enqueue_source_sync(
    session: AsyncSession,
    *,
    organization_id: UUID,
    source_selector: str,
    trigger: str,
) -> SourceSyncRun:
    """Queue only; the request path never runs provider I/O or historical work."""

    source = await resolve_data_source(
        session,
        organization_id=organization_id,
        selector=source_selector,
    )
    if not source.enabled:
        raise InvalidConfiguration("Enable the data source before queuing a sync")
    connection = await session.scalar(
        select(SourceConnection).where(SourceConnection.data_source_id == source.id)
    )
    active = await session.scalar(
        select(SourceSyncRun).where(
            SourceSyncRun.data_source_id == source.id,
            SourceSyncRun.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise ResourceConflict(f"Source already has an active sync: {active.id}")
    sync_run = SourceSyncRun(
        organization_id=organization_id,
        data_source_id=source.id,
        status="queued",
        trigger=trigger,
        cursor=connection.last_cursor if connection is not None else None,
    )
    session.add(sync_run)
    source.status = "queued"
    await session.flush()
    return sync_run


async def list_sync_runs(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int = 50,
) -> list[SourceSyncRun]:
    return list(
        await session.scalars(
            select(SourceSyncRun)
            .where(SourceSyncRun.organization_id == organization_id)
            .order_by(SourceSyncRun.created_at.desc())
            .limit(limit)
        )
    )


async def source_record_counts(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> dict[UUID, int]:
    rows = await session.execute(
        select(SourceRecord.data_source_id, func.count(SourceRecord.id))
        .where(SourceRecord.organization_id == organization_id)
        .group_by(SourceRecord.data_source_id)
    )
    return {source_id: int(count) for source_id, count in rows}


async def list_backup_snapshots(
    session: AsyncSession,
    *,
    limit: int = 20,
) -> list[BackupSnapshot]:
    return list(
        await session.scalars(
            select(BackupSnapshot).order_by(BackupSnapshot.started_at.desc()).limit(limit)
        )
    )


async def write_audit_log(
    session: AsyncSession,
    *,
    action: str,
    actor_type: str,
    organization_id: UUID | None = None,
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    request_id: str | None = None,
    details: dict[str, object] | None = None,
) -> AuditLog:
    entry = AuditLog(
        organization_id=organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        details=dict(details or {}),
    )
    session.add(entry)
    await session.flush()
    return entry


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


async def inspect_data(
    session: AsyncSession,
    *,
    organization_id: UUID,
    query: str,
    limit: int = 25,
) -> list[InspectorResult]:
    """Search canonical and source records without exposing raw object payloads."""

    term = query.strip()
    if not term:
        return []
    record_id = _uuid_or_none(term)
    pattern = f"%{term}%"
    results: list[InspectorResult] = []

    source_query = select(SourceRecord).where(SourceRecord.organization_id == organization_id)
    source_query = (
        source_query.where(SourceRecord.id == record_id)
        if record_id
        else source_query.where(SourceRecord.provider_record_id.ilike(pattern))
    )
    for item in await session.scalars(source_query.limit(limit)):
        results.append(
            InspectorResult(
                record_type="source_record",
                record_id=item.id,
                title=item.provider_record_id,
                subtitle=f"status={item.status} · source={item.data_source_id}",
                provenance=(
                    f"hash={item.raw_hash[:12]} · adapter={item.adapter_version} · "
                    f"normalization={item.normalization_version}"
                ),
                details={
                    "source_url": item.source_url or "",
                    "raw_object": (
                        f"{item.raw_object_bucket}/{item.raw_object_key}"
                        if item.raw_object_bucket and item.raw_object_key
                        else "not archived"
                    ),
                },
            )
        )

    remaining = max(limit - len(results), 0)
    if remaining:
        observation_query = select(Observation).where(
            Observation.organization_id == organization_id
        )
        observation_query = (
            observation_query.where(Observation.id == record_id)
            if record_id
            else observation_query.where(
                or_(
                    Observation.summary.ilike(pattern),
                    Observation.location_text.ilike(pattern),
                    Observation.observation_type.ilike(pattern),
                )
            )
        )
        for item in await session.scalars(observation_query.limit(remaining)):
            results.append(
                InspectorResult(
                    record_type="observation",
                    record_id=item.id,
                    title=item.summary,
                    subtitle=item.observation_type,
                    provenance=f"source_record={item.source_record_id or 'none'}",
                    spatial=(
                        f"{item.spatial_status} · region={item.region_id or 'unresolved'} · "
                        f"cell={item.terrain_cell_id or 'unresolved'}"
                    ),
                    details={"location": item.location_text or "unresolved"},
                )
            )

    remaining = max(limit - len(results), 0)
    if remaining:
        event_query = select(OperationalEvent).where(
            OperationalEvent.organization_id == organization_id
        )
        event_query = (
            event_query.where(OperationalEvent.id == record_id)
            if record_id
            else event_query.where(
                or_(
                    OperationalEvent.summary.ilike(pattern),
                    OperationalEvent.location_text.ilike(pattern),
                    OperationalEvent.callsign.ilike(pattern),
                    OperationalEvent.event_type.ilike(pattern),
                )
            )
        )
        for item in await session.scalars(event_query.limit(remaining)):
            results.append(
                InspectorResult(
                    record_type="operational_event",
                    record_id=item.id,
                    title=item.summary,
                    subtitle=f"{item.event_type} · callsign={item.callsign or 'unknown'}",
                    provenance=(
                        f"transmission={item.transmission_id} · transcript={item.transcript_id} · "
                        f"source={item.source}"
                    ),
                    spatial=(
                        f"{item.spatial_status or 'unresolved'} · "
                        f"region={item.region_id or 'unresolved'} · "
                        f"cell={item.terrain_cell_id or 'unresolved'}"
                    ),
                    details={"location": item.location_text or "unresolved"},
                )
            )

    remaining = max(limit - len(results), 0)
    if remaining:
        transmission_query = select(Transmission).where(
            Transmission.organization_id == organization_id
        )
        transmission_query = (
            transmission_query.where(Transmission.id == record_id)
            if record_id
            else transmission_query.where(
                or_(
                    Transmission.source_message_id.ilike(pattern),
                    Transmission.source_type.ilike(pattern),
                )
            )
        )
        for item in await session.scalars(transmission_query.limit(remaining)):
            results.append(
                InspectorResult(
                    record_type="transmission",
                    record_id=item.id,
                    title=item.source_message_id,
                    subtitle=f"source={item.source_type} · site={item.site_id}",
                )
            )

    remaining = max(limit - len(results), 0)
    if remaining:
        transcript_query = select(Transcript).where(Transcript.organization_id == organization_id)
        transcript_query = (
            transcript_query.where(Transcript.id == record_id)
            if record_id
            else transcript_query.where(
                or_(Transcript.raw_text.ilike(pattern), Transcript.normalized_text.ilike(pattern))
            )
        )
        for item in await session.scalars(transcript_query.limit(remaining)):
            results.append(
                InspectorResult(
                    record_type="transcript",
                    record_id=item.id,
                    title=item.normalized_text[:180],
                    subtitle=f"provider={item.provider} · transmission={item.transmission_id}",
                )
            )

    remaining = max(limit - len(results), 0)
    if remaining:
        region_query = select(Region).where(Region.organization_id == organization_id)
        region_query = (
            region_query.where(Region.id == record_id)
            if record_id
            else region_query.where(
                or_(
                    Region.region_code.ilike(pattern),
                    Region.name.ilike(pattern),
                    Region.provider_region_id.ilike(pattern),
                )
            )
        )
        for item in await session.scalars(region_query.limit(remaining)):
            results.append(
                InspectorResult(
                    record_type="region",
                    record_id=item.id,
                    title=f"{item.region_code} · {item.name}",
                    subtitle=f"{item.region_type} · provider={item.provider or 'TerraSatch'}",
                    spatial=item.spatial_status,
                )
            )

    remaining = max(limit - len(results), 0)
    if remaining:
        cell_query = select(TerrainCell).where(TerrainCell.organization_id == organization_id)
        cell_query = (
            cell_query.where(TerrainCell.id == record_id)
            if record_id
            else cell_query.where(TerrainCell.cell_id.ilike(pattern))
        )
        for item in await session.scalars(cell_query.limit(remaining)):
            results.append(
                InspectorResult(
                    record_type="terrain_cell",
                    record_id=item.id,
                    title=item.cell_id,
                    subtitle=f"region={item.region_id}",
                    spatial=item.spatial_status,
                )
            )

    return results[:limit]
