"""Additive canonical master-data and control-plane persistence models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin
from terrasatch.masterdata.spatial import Geometry


class DataSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned provider definition with independently controlled sync state."""

    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_data_sources_org_slug"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    adapter_version: Mapped[str | None] = mapped_column(String(64))
    normalization_version: Mapped[str] = mapped_column(String(64), default="1", nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="disconnected", nullable=False)
    sync_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class SourceConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Secretless provider connection and incremental cursor state."""

    __tablename__ = "source_connections"
    __table_args__ = (UniqueConstraint("data_source_id", name="uq_source_connections_data_source"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    data_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint_url: Mapped[str | None] = mapped_column(String(2048))
    credential_reference: Mapped[str | None] = mapped_column(String(255))
    last_cursor: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(String(512))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class SourceSyncRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One queued or completed provider sync with bounded counters."""

    __tablename__ = "source_sync_runs"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    data_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    cursor: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runtime_ms: Mapped[int | None] = mapped_column(Integer)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class SourceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provider record index with complete traceability to its original payload."""

    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "provider_record_id",
            name="uq_source_records_source_provider_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    data_source_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider_record_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_object_bucket: Mapped[str | None] = mapped_column(String(255))
    raw_object_key: Mapped[str | None] = mapped_column(String(2048))
    raw_content_type: Mapped[str | None] = mapped_column(String(255))
    raw_size_bytes: Mapped[int | None] = mapped_column(Integer)
    canonical_record_type: Mapped[str | None] = mapped_column(String(100))
    canonical_record_id: Mapped[UUID | None]
    adapter_version: Mapped[str] = mapped_column(String(64), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ingested", nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class Region(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stable forecast, provider, or operational region."""

    __tablename__ = "regions"
    __table_args__ = (
        UniqueConstraint("organization_id", "region_code", name="uq_regions_org_code"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    region_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    provider_region_id: Mapped[str | None] = mapped_column(String(255))
    geometry: Mapped[str | None] = mapped_column(Geometry("MULTIPOLYGON", 4326))
    spatial_status: Mapped[str] = mapped_column(String(32), default="unresolved", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attributes: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class TerrainCell(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stable TerraSatch spatial join key created only for configured pilot regions."""

    __tablename__ = "terrain_cells"
    __table_args__ = (
        UniqueConstraint("organization_id", "cell_id", name="uq_terrain_cells_org_cell_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    region_id: Mapped[UUID] = mapped_column(
        ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cell_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    geometry: Mapped[str | None] = mapped_column(Geometry("POLYGON", 4326))
    spatial_status: Mapped[str] = mapped_column(String(32), default="unresolved", nullable=False)
    min_elevation_ft: Mapped[int | None] = mapped_column(Integer)
    max_elevation_ft: Mapped[int | None] = mapped_column(Integer)
    mean_slope_degrees: Mapped[float | None] = mapped_column(Float)
    aspects: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    attributes: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TerrainCellSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Trace a stable cell to the source records that defined or enriched it."""

    __tablename__ = "terrain_cell_sources"
    __table_args__ = (
        UniqueConstraint(
            "terrain_cell_id",
            "source_record_id",
            name="uq_terrain_cell_sources_cell_record",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    terrain_cell_id: Mapped[UUID] = mapped_column(
        ForeignKey("terrain_cells.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_record_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship: Mapped[str] = mapped_column(String(64), default="derived_from", nullable=False)


class Observation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Normalized source fact; OperationalEvent remains the sole event architecture."""

    __tablename__ = "observations"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_records.id", ondelete="SET NULL"), unique=True
    )
    operational_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operational_events.id", ondelete="SET NULL"), index=True
    )
    region_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("regions.id", ondelete="SET NULL"), index=True
    )
    terrain_cell_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("terrain_cells.id", ondelete="SET NULL"), index=True
    )
    observation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    location_text: Mapped[str | None] = mapped_column(String(512))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    elevation_ft: Mapped[int | None] = mapped_column(Integer)
    aspect: Mapped[str | None] = mapped_column(String(8))
    confidence: Mapped[float | None] = mapped_column(Float)
    spatial_status: Mapped[str] = mapped_column(String(32), default="unresolved", nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class DataQualityFlag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Actionable issue tied to a canonical or source record."""

    __tablename__ = "data_quality_flags"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_records.id", ondelete="CASCADE"), index=True
    )
    observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("observations.id", ondelete="CASCADE"), index=True
    )
    operational_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operational_events.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), default="warning", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only operator and system action record."""

    __tablename__ = "audit_log"

    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(255), index=True)
    request_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class BackupSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Visibility record for PostgreSQL, OCI volume, and Object Storage backups."""

    __tablename__ = "backup_snapshots"

    backup_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location_reference: Mapped[str | None] = mapped_column(String(2048))
    restore_test_status: Mapped[str] = mapped_column(
        String(32), default="not_tested", nullable=False
    )
    restore_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
