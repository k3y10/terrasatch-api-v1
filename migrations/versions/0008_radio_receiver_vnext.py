"""Add RF provenance and aggregated Edge receiver telemetry.

Revision ID: 0008_radio_receiver_vnext
Revises: 0007_control_plane_master_data
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_radio_receiver_vnext"
down_revision = "0007_control_plane_master_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transmissions",
        sa.Column("rf_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "edge_devices",
        sa.Column("telemetry", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("edge_devices", "telemetry")
    op.drop_column("transmissions", "rf_metadata")
