"""Persist Satchy workspace chat history.
Revision ID: 0013_workspace_messages
Revises: 0012_billing_email_outbox
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_workspace_messages"
down_revision = "0012_billing_email_outbox"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_workspace_messages_organization_id", "workspace_messages", ["organization_id"]
    )
    op.create_index("ix_workspace_messages_user_id", "workspace_messages", ["user_id"])


def downgrade():
    op.drop_table("workspace_messages")
