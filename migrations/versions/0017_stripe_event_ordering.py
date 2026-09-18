"""Add Stripe event-order guards for subscription and invoice state.

Revision ID: 0017_stripe_event_ordering
Revises: 0016_account_recovery_email
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_stripe_event_ordering"
down_revision = "0016_account_recovery_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("last_subscription_event_created", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("last_invoice_event_created", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "stripe_events",
        sa.Column("provider_created_at", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stripe_events", "provider_created_at")
    op.drop_column("subscriptions", "last_invoice_event_created")
    op.drop_column("subscriptions", "last_subscription_event_created")
