"""Add durable billing email intents.
Revision ID: 0012_billing_email_outbox
Revises: 0011_subscription_billing
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_billing_email_outbox"
down_revision = "0011_subscription_billing"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_email_outbox",
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column(
            "activation_id", sa.Uuid(), sa.ForeignKey("billing_activations.id", ondelete="RESTRICT")
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("billing_email_outbox")
