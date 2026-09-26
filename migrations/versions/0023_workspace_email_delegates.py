"""Add explicit workspace email mailbox delegation.

Revision ID: 0023_workspace_email_delegates
Revises: 0022_workspace_email
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_workspace_email_delegates"
down_revision = "0022_workspace_email"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_email_delegates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mailbox_address", sa.String(320), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("can_send", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "mailbox_address",
            "user_id",
            name="uq_workspace_email_delegate_mailbox_user",
        ),
    )
    op.create_index(
        "ix_workspace_email_delegate_mailbox",
        "workspace_email_delegates",
        ["mailbox_address"],
    )
    op.create_index(
        "ix_workspace_email_delegate_user",
        "workspace_email_delegates",
        ["user_id"],
    )


def downgrade():
    op.drop_index(
        "ix_workspace_email_delegate_user",
        table_name="workspace_email_delegates",
    )
    op.drop_index(
        "ix_workspace_email_delegate_mailbox",
        table_name="workspace_email_delegates",
    )
    op.drop_table("workspace_email_delegates")
