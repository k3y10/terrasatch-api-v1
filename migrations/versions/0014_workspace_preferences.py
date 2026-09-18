"""Persist member workspace module choices."""

import sqlalchemy as sa
from alembic import op

revision = "0014_workspace_preferences"
down_revision = "0013_workspace_messages"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_preferences",
        sa.Column(
            "organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), primary_key=True
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("modules", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("workspace_preferences")
