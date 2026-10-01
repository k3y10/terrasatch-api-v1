"""Add organization-level workspace convergence profiles.

Revision ID: 0025_workspace_convergence
Revises: 0024_satchy_runs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_workspace_convergence"
down_revision = "0024_satchy_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_profiles",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "operational_domain",
            sa.String(length=64),
            server_default="general",
            nullable=False,
        ),
        sa.Column(
            "workspace_template",
            sa.String(length=100),
            server_default="general",
            nullable=False,
        ),
        sa.Column(
            "runtime_mode",
            sa.String(length=32),
            server_default="legacy",
            nullable=False,
        ),
        sa.Column(
            "recommended_modules",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "preferred_map_layers",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "workflow_preferences",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "discovery_state",
            sa.JSON(),
            server_default=sa.text("'{}'"),
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
        sa.PrimaryKeyConstraint("organization_id"),
    )


def downgrade() -> None:
    op.drop_table("workspace_profiles")
