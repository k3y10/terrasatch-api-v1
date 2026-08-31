"""Add Satchy evaluation, approval, outbound, and Edge command control plane.

Revision ID: 0010_satchy_action_control_plane
Revises: 0009_radio_conversations
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_satchy_action_control_plane"
down_revision = "0009_radio_conversations"
branch_labels = None
depends_on = None


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
    op.add_column(
        "transmissions",
        sa.Column("emergency_candidate", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("transmissions", sa.Column("emergency_confidence", sa.Float(), nullable=True))
    op.add_column("transmissions", sa.Column("emergency_reason", sa.Text(), nullable=True))

    op.create_table(
        "organization_operational_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("operation_type", sa.String(length=100), nullable=True),
        sa.Column("teams", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("roles", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("callsigns", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("radio_protocol", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("terminology", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("location_aliases", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("event_types", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("emergency_terms", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "site_id", name="uq_operational_profiles_org_site"),
    )
    op.create_index(
        "ix_organization_operational_profiles_organization_id",
        "organization_operational_profiles",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_operational_profiles_site_id",
        "organization_operational_profiles",
        ["site_id"],
    )

    op.create_table(
        "satchy_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("source_transmission_id", sa.Uuid(), nullable=False),
        sa.Column("addressed_to_satchy", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("interpretation", sa.Text(), nullable=False),
        sa.Column("proposed_action", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("approval_required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("emergency_candidate", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("emergency_confidence", sa.Float(), nullable=True),
        sa.Column("emergency_reason", sa.Text(), nullable=True),
        sa.Column("operational_context", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["radio_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_transmission_id"], ["transmissions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_transmission_id"),
        sa.CheckConstraint(
            "confidence >= 0 and confidence <= 1", name="ck_satchy_evaluations_confidence"
        ),
    )
    for column in ("organization_id", "site_id", "conversation_id", "source_transmission_id"):
        op.create_index(f"ix_satchy_evaluations_{column}", "satchy_evaluations", [column])

    op.create_table(
        "satchy_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("source_transmission_id", sa.Uuid(), nullable=False),
        sa.Column("operational_event_id", sa.Uuid(), nullable=True),
        sa.Column("evaluation_id", sa.Uuid(), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=32), server_default="low", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("proposed_message", sa.Text(), nullable=True),
        sa.Column("structured_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="proposed", nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["radio_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_transmission_id"], ["transmissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["operational_event_id"], ["operational_events.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["evaluation_id"], ["satchy_evaluations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "action_type in ('reply_radio', 'ask_clarification', 'create_observation', "
            "'update_event', 'notify_team', 'generate_report', 'emergency_review')",
            name="ck_satchy_actions_type",
        ),
        sa.CheckConstraint(
            "status in ('proposed', 'awaiting_approval', 'approved', 'queued', 'executing', "
            "'completed', 'rejected', 'expired', 'failed', 'cancelled')",
            name="ck_satchy_actions_status",
        ),
        sa.CheckConstraint(
            "confidence >= 0 and confidence <= 1",
            name="ck_satchy_actions_confidence",
        ),
    )
    for column in (
        "organization_id",
        "site_id",
        "conversation_id",
        "source_transmission_id",
        "operational_event_id",
        "evaluation_id",
        "action_type",
        "status",
        "expires_at",
    ):
        op.create_index(f"ix_satchy_actions_{column}", "satchy_actions", [column])
    op.create_index(
        "ix_satchy_actions_review_queue",
        "satchy_actions",
        ["organization_id", "status", "created_at"],
    )

    op.create_table(
        "action_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("approver_user_id", sa.Uuid(), nullable=True),
        sa.Column("approver_callsign_id", sa.Uuid(), nullable=True),
        sa.Column("approver_role", sa.String(length=64), nullable=False),
        sa.Column("approval_source", sa.String(length=32), nullable=False),
        sa.Column("source_transmission_id", sa.Uuid(), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["action_id"], ["satchy_actions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approver_callsign_id"], ["callsigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_transmission_id"], ["transmissions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "approval_source in ('console', 'radio', 'system_policy')",
            name="ck_action_approvals_source",
        ),
        sa.CheckConstraint(
            "decision in ('approved', 'rejected')", name="ck_action_approvals_decision"
        ),
    )
    for column in (
        "organization_id",
        "action_id",
        "approver_user_id",
        "approver_callsign_id",
        "source_transmission_id",
    ):
        op.create_index(f"ix_action_approvals_{column}", "action_approvals", [column])

    _create_outbound_tables()


def _create_outbound_tables() -> None:
    op.create_table(
        "outbound_transmissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("edge_device_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=True),
        sa.Column("speaker_callsign", sa.String(length=255), nullable=False),
        sa.Column("recipient_callsign", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=32), server_default="normal", nullable=False),
        sa.Column("reply_route", sa.String(length=32), server_default="simulation", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edge_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transmitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["edge_device_id"], ["edge_devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["action_id"], ["satchy_actions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["radio_conversations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id"),
        sa.CheckConstraint(
            "status in ('draft', 'queued', 'dispatched', 'edge_received', "
            "'waiting_channel_clear', 'simulated', 'transmitting', 'transmitted', "
            "'failed', 'expired', 'cancelled')",
            name="ck_outbound_transmissions_status",
        ),
    )
    for column in (
        "organization_id",
        "site_id",
        "edge_device_id",
        "action_id",
        "conversation_id",
        "channel_id",
        "status",
        "expires_at",
    ):
        op.create_index(f"ix_outbound_transmissions_{column}", "outbound_transmissions", [column])
    op.create_index(
        "ix_outbound_transmissions_device_queue",
        "outbound_transmissions",
        ["edge_device_id", "status", "queued_at"],
    )

    op.create_table(
        "edge_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("edge_device_id", sa.Uuid(), nullable=False),
        sa.Column("outbound_transmission_id", sa.Uuid(), nullable=True),
        sa.Column("command_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["edge_device_id"], ["edge_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["outbound_transmission_id"], ["outbound_transmissions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outbound_transmission_id"),
        sa.CheckConstraint(
            "status in ('queued', 'dispatched', 'acknowledged', 'completed', "
            "'failed', 'expired', 'cancelled')",
            name="ck_edge_commands_status",
        ),
    )
    for column in (
        "organization_id",
        "site_id",
        "edge_device_id",
        "outbound_transmission_id",
        "command_type",
        "status",
        "expires_at",
    ):
        op.create_index(f"ix_edge_commands_{column}", "edge_commands", [column])
    op.create_index(
        "ix_edge_commands_device_queue",
        "edge_commands",
        ["organization_id", "site_id", "edge_device_id", "status", "priority", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("edge_commands")
    op.drop_table("outbound_transmissions")
    op.drop_table("action_approvals")
    op.drop_table("satchy_actions")
    op.drop_table("satchy_evaluations")
    op.drop_table("organization_operational_profiles")
    op.drop_column("transmissions", "emergency_reason")
    op.drop_column("transmissions", "emergency_confidence")
    op.drop_column("transmissions", "emergency_candidate")
