"""Add append-only Satchy Discovery evidence events.

Revision ID: 0026_workspace_discovery_events
Revises: 0025_workspace_convergence
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_workspace_discovery_events"
down_revision = "0025_workspace_convergence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_discovery_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("supersedes_event_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("workflow_key", sa.String(length=128), nullable=True),
        sa.Column("workflow_label", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "evidence",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["sites.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_event_id"],
            ["workspace_discovery_events.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "dedupe_key",
            name="uq_workspace_discovery_events_org_dedupe",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "supersedes_event_id",
            name="uq_workspace_discovery_events_org_supersedes",
        ),
    )
    op.create_index(
        "ix_workspace_discovery_events_org_occurred",
        "workspace_discovery_events",
        ["organization_id", "occurred_at"],
    )
    op.create_index(
        "ix_workspace_discovery_events_org_workflow",
        "workspace_discovery_events",
        ["organization_id", "workflow_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_discovery_events_org_workflow",
        table_name="workspace_discovery_events",
    )
    op.drop_index(
        "ix_workspace_discovery_events_org_occurred",
        table_name="workspace_discovery_events",
    )
    op.drop_table("workspace_discovery_events")
