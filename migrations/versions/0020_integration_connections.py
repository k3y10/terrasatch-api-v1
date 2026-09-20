"""Add scoped external integration connections and encrypted credentials.

Revision ID: 0020_integration_connections
Revises: 0019_satchy_user_preferences
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_integration_connections"
down_revision = "0019_satchy_user_preferences"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="requested", nullable=False),
        sa.Column("configuration", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("provider_account_label", sa.String(length=255), nullable=True),
        sa.Column("provider_account_id", sa.String(length=255), nullable=True),
        sa.Column("credential_ref", sa.String(length=512), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id","provider","scope_type","team_id","owner_user_id","created_by_user_id","status"):
        op.create_index(f"ix_integration_connections_{column}", "integration_connections", [column])
    op.create_index("ix_integration_connections_scope","integration_connections",["organization_id","scope_type","team_id","owner_user_id"])
    op.create_index("ix_integration_connections_provider_status","integration_connections",["organization_id","provider","status"])

    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["connection_id"], ["integration_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", name="uq_integration_credentials_connection"),
    )
    op.create_index("ix_integration_credentials_organization_id","integration_credentials",["organization_id"])
    op.create_index("ix_integration_credentials_connection_id","integration_credentials",["connection_id"])

    op.create_table(
        "integration_oauth_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["connection_id"], ["integration_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash", name="uq_integration_oauth_states_hash"),
    )
    for column in ("organization_id","connection_id","user_id","provider"):
        op.create_index(f"ix_integration_oauth_states_{column}","integration_oauth_states",[column])
    op.create_index("ix_integration_oauth_states_expiry","integration_oauth_states",["provider","expires_at","consumed_at"])


def downgrade() -> None:
    op.drop_table("integration_oauth_states")
    op.drop_table("integration_credentials")
    op.drop_table("integration_connections")
