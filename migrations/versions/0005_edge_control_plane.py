"""Create TerraSatch Edge pairing and device tables.

Revision ID: 0005_edge_control_plane
Revises: 0004_radio_event_pipeline
Create Date: 2026-08-14 13:30:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_edge_control_plane"
down_revision: str | None = "0004_radio_event_pipeline"
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
    op.create_table(
        "edge_pairings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_code_hash", sa.String(length=128), nullable=False),
        sa.Column("user_code", sa.String(length=12), nullable=False),
        sa.Column("requested_name", sa.String(length=255), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("platform", sa.String(length=100), nullable=True),
        sa.Column("architecture", sa.String(length=100), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_api_key_id", sa.Uuid(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_api_key_id"], ["api_keys.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_code_hash"),
        sa.UniqueConstraint("user_code"),
    )
    op.create_index("ix_edge_pairings_user_code", "edge_pairings", ["user_code"])
    op.create_table(
        "edge_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("api_key_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("platform", sa.String(length=100), nullable=True),
        sa.Column("architecture", sa.String(length=100), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("hardware_inventory", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("remote_config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key_id", name="uq_edge_devices_api_key"),
    )
    op.create_index("ix_edge_devices_organization_id", "edge_devices", ["organization_id"])
    op.create_index("ix_edge_devices_site_id", "edge_devices", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_edge_devices_site_id", table_name="edge_devices")
    op.drop_index("ix_edge_devices_organization_id", table_name="edge_devices")
    op.drop_table("edge_devices")
    op.drop_index("ix_edge_pairings_user_code", table_name="edge_pairings")
    op.drop_table("edge_pairings")
