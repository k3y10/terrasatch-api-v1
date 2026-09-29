"""Add native TerraSatch form/version IDs and first-party distribution attribution.

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
        "feedback_distributions",
        sa.Column("distribution_id", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("placement", sa.String(length=255), nullable=True),
        sa.Column("audience_hint", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("distribution_id"),
    )
    op.create_index(
        "ix_feedback_distributions_distribution_id",
        "feedback_distributions",
        ["distribution_id"],
    )
    op.create_index(
        "ix_feedback_distributions_channel",
        "feedback_distributions",
        ["channel"],
    )

    op.create_table(
        "feedback_survey_responses",
        sa.Column("form_id", sa.String(length=64), nullable=False),
        sa.Column("form_version", sa.Integer(), nullable=False),
        sa.Column("distribution_id", sa.String(length=100), nullable=False),
        sa.Column("audience", sa.String(length=32), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("concept_interest", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_feedback_response_form_version",
        "feedback_survey_responses",
        ["form_id", "form_version"],
    )
    op.create_index(
        "ix_feedback_response_created_at",
        "feedback_survey_responses",
        ["created_at"],
    )
    op.create_index(
        "ix_feedback_response_distribution_id",
        "feedback_survey_responses",
        ["distribution_id"],
    )
    op.create_index(
        "ix_feedback_survey_responses_form_id",
        "feedback_survey_responses",
        ["form_id"],
    )
    op.create_index(
        "ix_feedback_survey_responses_audience",
        "feedback_survey_responses",
        ["audience"],
    )
    op.create_index(
        "ix_feedback_survey_responses_concept_interest",
        "feedback_survey_responses",
        ["concept_interest"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_feedback_survey_responses_concept_interest",
        table_name="feedback_survey_responses",
    )
    op.drop_index(
        "ix_feedback_survey_responses_audience",
        table_name="feedback_survey_responses",
    )
    op.drop_index(
        "ix_feedback_survey_responses_form_id",
        table_name="feedback_survey_responses",
    )
    op.drop_index(
        "ix_feedback_response_distribution_id",
        table_name="feedback_survey_responses",
    )
    op.drop_index(
        "ix_feedback_response_created_at",
        table_name="feedback_survey_responses",
    )
    op.drop_index(
        "ix_feedback_response_form_version",
        table_name="feedback_survey_responses",
    )
    op.drop_table("feedback_survey_responses")
    op.drop_index(
        "ix_feedback_distributions_channel",
        table_name="feedback_distributions",
    )
    op.drop_index(
        "ix_feedback_distributions_distribution_id",
        table_name="feedback_distributions",
    )
    op.drop_table("feedback_distributions")
