"""Add Resend-backed workspace email storage.

Revision ID: 0022_workspace_email
Revises: 0021_satchy_multichannel_actions
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_workspace_email"
down_revision = "0021_satchy_multichannel_actions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_email_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider_email_id", sa.String(255), nullable=False),
        sa.Column("provider_event_id", sa.String(255)),
        sa.Column("direction", sa.String(16), nullable=False, server_default="inbound"),
        sa.Column(
            "parent_email_id",
            sa.Uuid(),
            sa.ForeignKey("workspace_email_messages.id", ondelete="SET NULL"),
        ),
        sa.Column("recipient_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("internet_message_id", sa.String(1024)),
        sa.Column("received_for", sa.String(320), nullable=False),
        sa.Column("from_address", sa.String(1000), nullable=False),
        sa.Column("to_addresses", sa.JSON(), nullable=False),
        sa.Column("cc_addresses", sa.JSON(), nullable=False),
        sa.Column("bcc_addresses", sa.JSON(), nullable=False),
        sa.Column("reply_to", sa.JSON(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("text_body", sa.Text()),
        sa.Column("html_body", sa.Text()),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("provider_email_id", name="uq_workspace_email_provider_id"),
    )
    op.create_index(
        "ix_workspace_email_received_for",
        "workspace_email_messages",
        ["received_for"],
    )
    op.create_index(
        "ix_workspace_email_received_at",
        "workspace_email_messages",
        ["received_at"],
    )
    op.create_index(
        "ix_workspace_email_parent_id",
        "workspace_email_messages",
        ["parent_email_id"],
    )
    op.create_index(
        "ix_workspace_email_messages_recipient_user_id",
        "workspace_email_messages",
        ["recipient_user_id"],
    )
    op.create_table(
        "workspace_email_reads",
        sa.Column(
            "email_id",
            sa.Uuid(),
            sa.ForeignKey("workspace_email_messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("workspace_email_reads")
    op.drop_index("ix_workspace_email_messages_recipient_user_id", table_name="workspace_email_messages")
    op.drop_index("ix_workspace_email_parent_id", table_name="workspace_email_messages")
    op.drop_index("ix_workspace_email_received_at", table_name="workspace_email_messages")
    op.drop_index("ix_workspace_email_received_for", table_name="workspace_email_messages")
    op.drop_table("workspace_email_messages")
