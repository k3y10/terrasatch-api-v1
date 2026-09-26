"""Add platform superadmin capability to users.

Revision ID: 0024_user_superadmin
Revises: 0023_workspace_email_delegates
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_user_superadmin"
down_revision = "0023_workspace_email_delegates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_superadmin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("users", "is_superadmin")
