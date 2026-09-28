"""Add native TerraSatch feedback campaigns, responses, sources, and giveaway entries.

Revision ID: 0022_native_feedback
Revises: 0021_satchy_multichannel_actions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_native_feedback"
down_revision = "0021_satchy_multichannel_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_survey_campaigns",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_feedback_survey_campaigns_slug", "feedback_survey_campaigns", ["slug"])
    op.create_table(
        "feedback_survey_sources",
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["feedback_survey_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "code", name="uq_feedback_source_campaign_code"),
    )
    op.create_index("ix_feedback_survey_sources_campaign_id", "feedback_survey_sources", ["campaign_id"])
    op.create_table(
        "feedback_survey_responses",
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source_code", sa.String(length=100), nullable=False),
        sa.Column("audience", sa.String(length=32), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("concept_interest", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["feedback_survey_campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["feedback_survey_sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_response_campaign_created", "feedback_survey_responses", ["campaign_id", "created_at"])
    op.create_index("ix_feedback_response_source_code", "feedback_survey_responses", ["source_code"])
    op.create_index("ix_feedback_survey_responses_audience", "feedback_survey_responses", ["audience"])
    op.create_index("ix_feedback_survey_responses_concept_interest", "feedback_survey_responses", ["concept_interest"])
    op.create_table(
        "feedback_giveaway_campaigns",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("official_rules_url", sa.String(length=1000), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_feedback_giveaway_campaigns_slug", "feedback_giveaway_campaigns", ["slug"])
    op.create_table(
        "feedback_giveaway_entries",
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("resort_preference", sa.String(length=32), nullable=False),
        sa.Column("rules_accepted", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["feedback_giveaway_campaigns.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "email", name="uq_feedback_giveaway_campaign_email"),
    )
    op.create_index("ix_feedback_giveaway_entries_campaign_id", "feedback_giveaway_entries", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_giveaway_entries_campaign_id", table_name="feedback_giveaway_entries")
    op.drop_table("feedback_giveaway_entries")
    op.drop_index("ix_feedback_giveaway_campaigns_slug", table_name="feedback_giveaway_campaigns")
    op.drop_table("feedback_giveaway_campaigns")
    op.drop_index("ix_feedback_survey_responses_concept_interest", table_name="feedback_survey_responses")
    op.drop_index("ix_feedback_survey_responses_audience", table_name="feedback_survey_responses")
    op.drop_index("ix_feedback_response_source_code", table_name="feedback_survey_responses")
    op.drop_index("ix_feedback_response_campaign_created", table_name="feedback_survey_responses")
    op.drop_table("feedback_survey_responses")
    op.drop_index("ix_feedback_survey_sources_campaign_id", table_name="feedback_survey_sources")
    op.drop_table("feedback_survey_sources")
    op.drop_index("ix_feedback_survey_campaigns_slug", table_name="feedback_survey_campaigns")
    op.drop_table("feedback_survey_campaigns")
