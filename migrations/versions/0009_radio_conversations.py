"""Add deterministic radio conversations and callsign addressing.

Revision ID: 0009_radio_conversations
Revises: 0008_radio_receiver_vnext
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_radio_conversations"
down_revision = "0008_radio_receiver_vnext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "radio_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("primary_topic", sa.String(length=255), nullable=True),
        sa.Column("active_location", sa.String(length=255), nullable=True),
        sa.Column("operational_event_id", sa.Uuid(), nullable=True),
        sa.Column("participants", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("participant_fingerprint", sa.String(length=512), nullable=False),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["operational_event_id"], ["operational_events.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status in ('open', 'closed', 'expired')",
            name="ck_radio_conversations_status",
        ),
    )
    op.create_index(
        "ix_radio_conversations_active_lookup",
        "radio_conversations",
        ["organization_id", "site_id", "channel_id", "status", "last_activity_at"],
    )
    op.create_index(
        "ix_radio_conversations_participants",
        "radio_conversations",
        ["organization_id", "participant_fingerprint"],
    )
    op.create_index(
        "ix_radio_conversations_organization_id", "radio_conversations", ["organization_id"]
    )
    op.create_index("ix_radio_conversations_site_id", "radio_conversations", ["site_id"])
    op.create_index("ix_radio_conversations_channel_id", "radio_conversations", ["channel_id"])
    op.create_index(
        "ix_radio_conversations_operational_event_id",
        "radio_conversations",
        ["operational_event_id"],
    )

    op.add_column("transmissions", sa.Column("conversation_id", sa.Uuid(), nullable=True))
    op.add_column("transmissions", sa.Column("speaker_callsign_id", sa.Uuid(), nullable=True))
    op.add_column("transmissions", sa.Column("recipient_callsign_id", sa.Uuid(), nullable=True))
    op.add_column("transmissions", sa.Column("speaker_text", sa.String(length=255), nullable=True))
    op.add_column(
        "transmissions", sa.Column("recipient_text", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "transmissions",
        sa.Column("addressed_to_agent", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("transmissions", sa.Column("addressing_confidence", sa.Float(), nullable=True))
    op.create_foreign_key(
        "fk_transmissions_conversation_id_radio_conversations",
        "transmissions",
        "radio_conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transmissions_speaker_callsign_id_callsigns",
        "transmissions",
        "callsigns",
        ["speaker_callsign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_transmissions_recipient_callsign_id_callsigns",
        "transmissions",
        "callsigns",
        ["recipient_callsign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transmissions_conversation_id", "transmissions", ["conversation_id"])
    op.create_index(
        "ix_transmissions_speaker_callsign_id", "transmissions", ["speaker_callsign_id"]
    )
    op.create_index(
        "ix_transmissions_recipient_callsign_id", "transmissions", ["recipient_callsign_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_transmissions_recipient_callsign_id", table_name="transmissions")
    op.drop_index("ix_transmissions_speaker_callsign_id", table_name="transmissions")
    op.drop_index("ix_transmissions_conversation_id", table_name="transmissions")
    op.drop_constraint(
        "fk_transmissions_recipient_callsign_id_callsigns", "transmissions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_transmissions_speaker_callsign_id_callsigns", "transmissions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_transmissions_conversation_id_radio_conversations",
        "transmissions",
        type_="foreignkey",
    )
    op.drop_column("transmissions", "addressing_confidence")
    op.drop_column("transmissions", "addressed_to_agent")
    op.drop_column("transmissions", "recipient_text")
    op.drop_column("transmissions", "speaker_text")
    op.drop_column("transmissions", "recipient_callsign_id")
    op.drop_column("transmissions", "speaker_callsign_id")
    op.drop_column("transmissions", "conversation_id")
    op.drop_table("radio_conversations")
