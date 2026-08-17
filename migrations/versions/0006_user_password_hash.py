"""Add optional local browser password hash for organization users.

Revision ID: 0006_user_password_hash
Revises: 0005_edge_control_plane
Create Date: 2026-08-17 15:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_user_password_hash"
down_revision: str | None = "0005_edge_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
