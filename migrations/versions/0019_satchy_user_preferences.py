"""Add private Satchy user adaptation preferences.

Revision ID: 0019_satchy_user_preferences
Revises: 0018_satchy_assets_missions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_satchy_user_preferences"
down_revision = "0018_satchy_assets_missions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_preferences",
        sa.Column(
            "satchy_preferences",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("workspace_preferences", "satchy_preferences")
