"""Allow Satchy actions to originate outside radio transmissions.

Revision ID: 0021_satchy_multichannel_actions
Revises: 0020_integration_connections
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_satchy_multichannel_actions"
down_revision = "0020_integration_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "satchy_actions",
        "conversation_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.alter_column(
        "satchy_actions",
        "source_transmission_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM satchy_actions "
        "WHERE conversation_id IS NULL OR source_transmission_id IS NULL"
    )
    op.alter_column(
        "satchy_actions",
        "source_transmission_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "satchy_actions",
        "conversation_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
