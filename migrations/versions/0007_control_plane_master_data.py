"""Add canonical source, provenance, PostGIS pilot, audit, and backup visibility.

Revision ID: 0007_control_plane_master_data
Revises: 0006_user_password_hash
Create Date: 2026-08-19 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from terrasatch.masterdata.spatial import Geometry

revision: str = "0007_control_plane_master_data"
down_revision: str | None = "0006_user_password_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "data_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("adapter_key", sa.String(length=100), nullable=False),
        sa.Column("adapter_version", sa.String(length=64), nullable=True),
        sa.Column(
            "normalization_version",
            sa.String(length=64),
            server_default=sa.text("'1'"),
            nullable=False,
        ),
        sa.Column("configuration", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'disconnected'"),
            nullable=False,
        ),
        sa.Column("sync_interval_seconds", sa.Integer(), nullable=True),
        sa.Column("last_attempt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_data_sources_org_slug"),
    )
    op.create_index("ix_data_sources_organization_id", "data_sources", ["organization_id"])
    op.create_index("ix_data_sources_provider", "data_sources", ["provider"])

    op.create_table(
        "source_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_url", sa.String(length=2048), nullable=True),
        sa.Column("credential_reference", sa.String(length=255), nullable=True),
        sa.Column("last_cursor", sa.Text(), nullable=True),
        sa.Column("etag", sa.String(length=512), nullable=True),
        sa.Column("last_modified", sa.String(length=255), nullable=True),
        sa.Column("state", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_source_id", name="uq_source_connections_data_source"),
    )
    op.create_index(
        "ix_source_connections_organization_id", "source_connections", ["organization_id"]
    )
    op.create_index(
        "ix_source_connections_data_source_id", "source_connections", ["data_source_id"]
    )

    op.create_table(
        "source_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "trigger",
            sa.String(length=32),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rejected_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_sync_runs_organization_id", "source_sync_runs", ["organization_id"])
    op.create_index("ix_source_sync_runs_data_source_id", "source_sync_runs", ["data_source_id"])
    op.create_index("ix_source_sync_runs_status", "source_sync_runs", ["status"])

    op.create_table(
        "source_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("provider_record_id", sa.String(length=512), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_hash", sa.String(length=128), nullable=False),
        sa.Column("raw_object_bucket", sa.String(length=255), nullable=True),
        sa.Column("raw_object_key", sa.String(length=2048), nullable=True),
        sa.Column("raw_content_type", sa.String(length=255), nullable=True),
        sa.Column("raw_size_bytes", sa.Integer(), nullable=True),
        sa.Column("canonical_record_type", sa.String(length=100), nullable=True),
        sa.Column("canonical_record_id", sa.Uuid(), nullable=True),
        sa.Column("adapter_version", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'ingested'"),
            nullable=False,
        ),
        sa.Column("metadata_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id",
            "provider_record_id",
            name="uq_source_records_source_provider_id",
        ),
    )
    op.create_index("ix_source_records_organization_id", "source_records", ["organization_id"])
    op.create_index("ix_source_records_data_source_id", "source_records", ["data_source_id"])
    op.create_index(
        "ix_source_records_provider_record_id", "source_records", ["provider_record_id"]
    )

    op.create_table(
        "regions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("region_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("region_type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("provider_region_id", sa.String(length=255), nullable=True),
        sa.Column("geometry", Geometry("MULTIPOLYGON", 4326), nullable=True),
        sa.Column(
            "spatial_status",
            sa.String(length=32),
            server_default=sa.text("'unresolved'"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("attributes", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "region_code", name="uq_regions_org_code"),
    )
    op.create_index("ix_regions_organization_id", "regions", ["organization_id"])
    op.create_index("ix_regions_region_code", "regions", ["region_code"])
    if dialect_name == "postgresql":
        op.create_index(
            "ix_regions_geometry_gist",
            "regions",
            ["geometry"],
            postgresql_using="gist",
        )

    op.create_table(
        "terrain_cells",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("region_id", sa.Uuid(), nullable=False),
        sa.Column("cell_id", sa.String(length=100), nullable=False),
        sa.Column("geometry", Geometry("POLYGON", 4326), nullable=True),
        sa.Column(
            "spatial_status",
            sa.String(length=32),
            server_default=sa.text("'unresolved'"),
            nullable=False,
        ),
        sa.Column("min_elevation_ft", sa.Integer(), nullable=True),
        sa.Column("max_elevation_ft", sa.Integer(), nullable=True),
        sa.Column("mean_slope_degrees", sa.Float(), nullable=True),
        sa.Column("aspects", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("attributes", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "cell_id", name="uq_terrain_cells_org_cell_id"),
    )
    op.create_index("ix_terrain_cells_organization_id", "terrain_cells", ["organization_id"])
    op.create_index("ix_terrain_cells_region_id", "terrain_cells", ["region_id"])
    op.create_index("ix_terrain_cells_cell_id", "terrain_cells", ["cell_id"])
    if dialect_name == "postgresql":
        op.create_index(
            "ix_terrain_cells_geometry_gist",
            "terrain_cells",
            ["geometry"],
            postgresql_using="gist",
        )

    op.create_table(
        "terrain_cell_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("terrain_cell_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.Uuid(), nullable=False),
        sa.Column(
            "relationship",
            sa.String(length=64),
            server_default=sa.text("'derived_from'"),
            nullable=False,
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["terrain_cell_id"], ["terrain_cells.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "terrain_cell_id",
            "source_record_id",
            name="uq_terrain_cell_sources_cell_record",
        ),
    )
    op.create_index(
        "ix_terrain_cell_sources_organization_id",
        "terrain_cell_sources",
        ["organization_id"],
    )
    op.create_index(
        "ix_terrain_cell_sources_terrain_cell_id",
        "terrain_cell_sources",
        ["terrain_cell_id"],
    )
    op.create_index(
        "ix_terrain_cell_sources_source_record_id",
        "terrain_cell_sources",
        ["source_record_id"],
    )

    op.add_column("operational_events", sa.Column("region_id", sa.Uuid(), nullable=True))
    op.add_column("operational_events", sa.Column("terrain_cell_id", sa.Uuid(), nullable=True))
    op.add_column(
        "operational_events", sa.Column("spatial_status", sa.String(length=32), nullable=True)
    )
    op.create_foreign_key(
        "fk_operational_events_region_id_regions",
        "operational_events",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_operational_events_terrain_cell_id_terrain_cells",
        "operational_events",
        "terrain_cells",
        ["terrain_cell_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_operational_events_region_id", "operational_events", ["region_id"])
    op.create_index(
        "ix_operational_events_terrain_cell_id", "operational_events", ["terrain_cell_id"]
    )

    op.create_table(
        "observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.Uuid(), nullable=True),
        sa.Column("operational_event_id", sa.Uuid(), nullable=True),
        sa.Column("region_id", sa.Uuid(), nullable=True),
        sa.Column("terrain_cell_id", sa.Uuid(), nullable=True),
        sa.Column("observation_type", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("location_text", sa.String(length=512), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("elevation_ft", sa.Integer(), nullable=True),
        sa.Column("aspect", sa.String(length=8), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "spatial_status",
            sa.String(length=32),
            server_default=sa.text("'unresolved'"),
            nullable=False,
        ),
        sa.Column("data", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["operational_event_id"], ["operational_events.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["terrain_cell_id"], ["terrain_cells.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_record_id", name="uq_observations_source_record"),
    )
    op.create_index("ix_observations_organization_id", "observations", ["organization_id"])
    op.create_index(
        "ix_observations_operational_event_id", "observations", ["operational_event_id"]
    )
    op.create_index("ix_observations_region_id", "observations", ["region_id"])
    op.create_index("ix_observations_terrain_cell_id", "observations", ["terrain_cell_id"])
    op.create_index("ix_observations_observation_type", "observations", ["observation_type"])
    op.create_index("ix_observations_observed_at", "observations", ["observed_at"])

    op.create_table(
        "data_quality_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_record_id", sa.Uuid(), nullable=True),
        sa.Column("observation_id", sa.Uuid(), nullable=True),
        sa.Column("operational_event_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column(
            "severity",
            sa.String(length=32),
            server_default=sa.text("'warning'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'open'"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["operational_event_id"], ["operational_events.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_quality_flags_organization_id", "data_quality_flags", ["organization_id"]
    )
    op.create_index(
        "ix_data_quality_flags_source_record_id", "data_quality_flags", ["source_record_id"]
    )
    op.create_index(
        "ix_data_quality_flags_observation_id", "data_quality_flags", ["observation_id"]
    )
    op.create_index(
        "ix_data_quality_flags_operational_event_id",
        "data_quality_flags",
        ["operational_event_id"],
    )
    op.create_index("ix_data_quality_flags_code", "data_quality_flags", ["code"])
    op.create_index("ix_data_quality_flags_status", "data_quality_flags", ["status"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=True),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_organization_id", "audit_log", ["organization_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_target_id", "audit_log", ["target_id"])

    op.create_table(
        "backup_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("backup_type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location_reference", sa.String(length=2048), nullable=True),
        sa.Column(
            "restore_test_status",
            sa.String(length=32),
            server_default=sa.text("'not_tested'"),
            nullable=False,
        ),
        sa.Column("restore_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backup_snapshots_backup_type", "backup_snapshots", ["backup_type"])
    op.create_index("ix_backup_snapshots_status", "backup_snapshots", ["status"])


def downgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    op.drop_index("ix_backup_snapshots_status", table_name="backup_snapshots")
    op.drop_index("ix_backup_snapshots_backup_type", table_name="backup_snapshots")
    op.drop_table("backup_snapshots")
    op.drop_index("ix_audit_log_target_id", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_organization_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_data_quality_flags_status", table_name="data_quality_flags")
    op.drop_index("ix_data_quality_flags_code", table_name="data_quality_flags")
    op.drop_index("ix_data_quality_flags_operational_event_id", table_name="data_quality_flags")
    op.drop_index("ix_data_quality_flags_observation_id", table_name="data_quality_flags")
    op.drop_index("ix_data_quality_flags_source_record_id", table_name="data_quality_flags")
    op.drop_index("ix_data_quality_flags_organization_id", table_name="data_quality_flags")
    op.drop_table("data_quality_flags")
    op.drop_index("ix_observations_observed_at", table_name="observations")
    op.drop_index("ix_observations_observation_type", table_name="observations")
    op.drop_index("ix_observations_terrain_cell_id", table_name="observations")
    op.drop_index("ix_observations_region_id", table_name="observations")
    op.drop_index("ix_observations_operational_event_id", table_name="observations")
    op.drop_index("ix_observations_organization_id", table_name="observations")
    op.drop_table("observations")
    op.drop_index("ix_operational_events_terrain_cell_id", table_name="operational_events")
    op.drop_index("ix_operational_events_region_id", table_name="operational_events")
    op.drop_constraint(
        "fk_operational_events_terrain_cell_id_terrain_cells",
        "operational_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_operational_events_region_id_regions", "operational_events", type_="foreignkey"
    )
    op.drop_column("operational_events", "spatial_status")
    op.drop_column("operational_events", "terrain_cell_id")
    op.drop_column("operational_events", "region_id")
    op.drop_index("ix_terrain_cell_sources_source_record_id", table_name="terrain_cell_sources")
    op.drop_index("ix_terrain_cell_sources_terrain_cell_id", table_name="terrain_cell_sources")
    op.drop_index("ix_terrain_cell_sources_organization_id", table_name="terrain_cell_sources")
    op.drop_table("terrain_cell_sources")
    if dialect_name == "postgresql":
        op.drop_index("ix_terrain_cells_geometry_gist", table_name="terrain_cells")
    op.drop_index("ix_terrain_cells_cell_id", table_name="terrain_cells")
    op.drop_index("ix_terrain_cells_region_id", table_name="terrain_cells")
    op.drop_index("ix_terrain_cells_organization_id", table_name="terrain_cells")
    op.drop_table("terrain_cells")
    if dialect_name == "postgresql":
        op.drop_index("ix_regions_geometry_gist", table_name="regions")
    op.drop_index("ix_regions_region_code", table_name="regions")
    op.drop_index("ix_regions_organization_id", table_name="regions")
    op.drop_table("regions")
    op.drop_index("ix_source_records_provider_record_id", table_name="source_records")
    op.drop_index("ix_source_records_data_source_id", table_name="source_records")
    op.drop_index("ix_source_records_organization_id", table_name="source_records")
    op.drop_table("source_records")
    op.drop_index("ix_source_sync_runs_status", table_name="source_sync_runs")
    op.drop_index("ix_source_sync_runs_data_source_id", table_name="source_sync_runs")
    op.drop_index("ix_source_sync_runs_organization_id", table_name="source_sync_runs")
    op.drop_table("source_sync_runs")
    op.drop_index("ix_source_connections_data_source_id", table_name="source_connections")
    op.drop_index("ix_source_connections_organization_id", table_name="source_connections")
    op.drop_table("source_connections")
    op.drop_index("ix_data_sources_provider", table_name="data_sources")
    op.drop_index("ix_data_sources_organization_id", table_name="data_sources")
    op.drop_table("data_sources")
