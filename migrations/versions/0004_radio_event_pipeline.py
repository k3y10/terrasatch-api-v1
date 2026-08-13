"""Create radio pipeline and operational event tables.

Revision ID: 0004_radio_event_pipeline
Revises: 0003_api_key_hash_index
Create Date: 2026-08-13 01:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_radio_event_pipeline"
down_revision: str | None = "0003_api_key_hash_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("profile", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_agents_org_slug"),
    )
    op.create_index("ix_agents_organization_id", "agents", ["organization_id"])

    op.create_table(
        "channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("profile", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_channels_org_slug"),
    )
    op.create_index("ix_channels_organization_id", "channels", ["organization_id"])

    op.create_table(
        "callsigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_callsigns_org_name"),
    )
    op.create_index("ix_callsigns_organization_id", "callsigns", ["organization_id"])

    op.create_table(
        "transmissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("channel_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_message_id", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "source_message_id",
            name="uq_transmissions_org_source_message",
        ),
    )
    op.create_index("ix_transmissions_organization_id", "transmissions", ["organization_id"])

    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transmission_id", sa.Uuid(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("processing_latency_ms", sa.Integer(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transmission_id"], ["transmissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transmission_id", name="uq_transcripts_transmission_id"),
    )
    op.create_index("ix_transcripts_organization_id", "transcripts", ["organization_id"])

    op.create_table(
        "operational_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("transmission_id", sa.Uuid(), nullable=False),
        sa.Column("transcript_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("callsign", sa.String(length=255), nullable=True),
        sa.Column("location_text", sa.String(length=255), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("elevation_ft", sa.Integer(), nullable=True),
        sa.Column("aspect", sa.String(length=8), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transmission_id"], ["transmissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operational_events_organization_id", "operational_events", ["organization_id"])
    op.create_index("ix_operational_events_transmission_id", "operational_events", ["transmission_id"])
    op.create_index("ix_operational_events_transcript_id", "operational_events", ["transcript_id"])
    op.create_index("ix_operational_events_event_type", "operational_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_operational_events_event_type", table_name="operational_events")
    op.drop_index("ix_operational_events_transcript_id", table_name="operational_events")
    op.drop_index("ix_operational_events_transmission_id", table_name="operational_events")
    op.drop_index("ix_operational_events_organization_id", table_name="operational_events")
    op.drop_table("operational_events")
    op.drop_index("ix_transcripts_organization_id", table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_index("ix_transmissions_organization_id", table_name="transmissions")
    op.drop_table("transmissions")
    op.drop_index("ix_callsigns_organization_id", table_name="callsigns")
    op.drop_table("callsigns")
    op.drop_index("ix_channels_organization_id", table_name="channels")
    op.drop_table("channels")
    op.drop_index("ix_agents_organization_id", table_name="agents")
    op.drop_table("agents")
