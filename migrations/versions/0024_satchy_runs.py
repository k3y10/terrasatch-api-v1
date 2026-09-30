"""Add persistent Satchy workspace runs and activity steps.

Revision ID: 0024_satchy_runs
Revises: 0023_feedback_campaign_variants
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_satchy_runs"
down_revision = "0023_feedback_campaign_variants"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column[object]]:
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
        "satchy_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="running", nullable=False),
        sa.Column("run_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "request_id",
            name="uq_satchy_runs_request",
        ),
    )
    for column in ("organization_id", "site_id", "user_id", "request_id", "status"):
        op.create_index(f"ix_satchy_runs_{column}", "satchy_runs", [column])
    op.create_index(
        "ix_satchy_runs_user_recent",
        "satchy_runs",
        ["organization_id", "user_id", "created_at"],
    )
    op.create_index(
        "ix_satchy_runs_status_recent",
        "satchy_runs",
        ["organization_id", "status", "created_at"],
    )

    op.create_table(
        "satchy_run_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("source_refs", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["satchy_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["action_id"], ["satchy_actions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_satchy_run_steps_sequence"),
    )
    for column in ("organization_id", "run_id", "action_id", "step_type", "status"):
        op.create_index(f"ix_satchy_run_steps_{column}", "satchy_run_steps", [column])
    op.create_index(
        "ix_satchy_run_steps_run",
        "satchy_run_steps",
        ["organization_id", "run_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_table("satchy_run_steps")
    op.drop_table("satchy_runs")
