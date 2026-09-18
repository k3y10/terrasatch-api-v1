"""Track transactional billing email provider receipts.
Revision ID: 0015_billing_email_receipts
Revises: 0014_workspace_preferences
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_billing_email_receipts"
down_revision = "0014_workspace_preferences"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "billing_email_outbox",
        sa.Column("delivery_provider", sa.String(64), nullable=True),
    )
    op.add_column(
        "billing_email_outbox",
        sa.Column("provider_message_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "billing_email_outbox",
        sa.Column("delivery_status", sa.String(64), nullable=True),
    )
    op.add_column(
        "billing_email_outbox",
        sa.Column("provider_event_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "billing_email_outbox",
        sa.Column("provider_event_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "billing_email_outbox",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("billing_email_outbox", "delivered_at")
    op.drop_column("billing_email_outbox", "provider_event_at")
    op.drop_column("billing_email_outbox", "provider_event_id")
    op.drop_column("billing_email_outbox", "delivery_status")
    op.drop_column("billing_email_outbox", "provider_message_id")
    op.drop_column("billing_email_outbox", "delivery_provider")
