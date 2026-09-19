"""Add Satchy field assets and mission planning.

Revision ID: 0018_satchy_assets_missions
Revises: 0017_stripe_event_ordering
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_satchy_assets_missions"
down_revision = "0017_stripe_event_ordering"
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
    op.drop_constraint("ck_satchy_actions_type", "satchy_actions", type_="check")
    op.create_check_constraint(
        "ck_satchy_actions_type",
        "satchy_actions",
        "action_type in ('reply_radio', 'ask_clarification', 'create_observation', "
        "'update_event', 'notify_team', 'generate_report', 'emergency_review', 'asset_mission')",
    )

    op.create_table(
        "field_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("controller_edge_device_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("capabilities", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="offline", nullable=False),
        sa.Column("location", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("policy", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["controller_edge_device_id"], ["edge_devices.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_field_assets_org_name"),
    )
    for column in (
        "organization_id",
        "site_id",
        "team_id",
        "owner_user_id",
        "controller_edge_device_id",
        "asset_type",
        "state",
    ):
        op.create_index(f"ix_field_assets_{column}", "field_assets", [column])
    op.create_index(
        "ix_field_assets_scope",
        "field_assets",
        ["organization_id", "site_id", "team_id", "owner_user_id"],
    )

    op.create_table(
        "field_missions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_callsign_id", sa.Uuid(), nullable=True),
        sa.Column("source_transmission_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("edge_command_id", sa.Uuid(), nullable=True),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("mission_type", sa.String(length=100), nullable=False),
        sa.Column("required_capabilities", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("target", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("parameters", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("risk_level", sa.String(length=32), server_default="moderate", nullable=False),
        sa.Column("approval_required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="proposed", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["asset_id"], ["field_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["requested_by_callsign_id"], ["callsigns.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_transmission_id"], ["transmissions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["radio_conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["action_id"], ["satchy_actions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["edge_command_id"], ["edge_commands.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id"),
        sa.UniqueConstraint("edge_command_id"),
    )
    for column in (
        "organization_id",
        "site_id",
        "asset_id",
        "requested_by_user_id",
        "requested_by_callsign_id",
        "source_transmission_id",
        "conversation_id",
        "action_id",
        "edge_command_id",
        "mission_type",
        "status",
    ):
        op.create_index(f"ix_field_missions_{column}", "field_missions", [column])
    op.create_index(
        "ix_field_missions_queue",
        "field_missions",
        ["organization_id", "site_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("field_missions")
    op.drop_table("field_assets")
    op.drop_constraint("ck_satchy_actions_type", "satchy_actions", type_="check")
    op.create_check_constraint(
        "ck_satchy_actions_type",
        "satchy_actions",
        "action_type in ('reply_radio', 'ask_clarification', 'create_observation', "
        "'update_event', 'notify_team', 'generate_report', 'emergency_review')",
    )
