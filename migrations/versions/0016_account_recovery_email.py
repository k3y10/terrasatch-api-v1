"""Add durable TerraSatch account-recovery email state.

Revision ID: 0016_account_recovery_email
Revises: 0015_billing_email_receipts
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_account_recovery_email"
down_revision = "0015_billing_email_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_intents_token_hash"),
    )
    op.create_index(
        "ix_password_reset_intents_user_id",
        "password_reset_intents",
        ["user_id"],
    )
    op.add_column(
        "billing_email_outbox",
        sa.Column("password_reset_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_billing_email_outbox_password_reset",
        "billing_email_outbox",
        "password_reset_intents",
        ["password_reset_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_billing_email_outbox_password_reset",
        "billing_email_outbox",
        type_="foreignkey",
    )
    op.drop_column("billing_email_outbox", "password_reset_id")
    op.drop_index("ix_password_reset_intents_user_id", table_name="password_reset_intents")
    op.drop_table("password_reset_intents")
