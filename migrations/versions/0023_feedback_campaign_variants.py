"""Register first-party TerraSatch feedback campaign variants.

Revision ID: 0023_feedback_campaign_variants
Revises: 0022_native_feedback
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = "0023_feedback_campaign_variants"
down_revision = "0022_native_feedback"
branch_labels = None
depends_on = None

_CAMPAIGNS = (
    {
        "id": UUID("0d1ef32e-0c15-4e62-9da2-3bb2db2c2bc1"),
        "distribution_id": "BRIGHTON-QR-01",
        "label": "Brighton QR - Field Check-In",
        "channel": "qr",
        "placement": "Brighton / Wasatch Front",
        "audience_hint": "recreation",
        "metadata_json": {
            "campaign": "brighton",
            "form_version": 3,
            "canonical_url": "https://www.terrasatch.com/check-in",
        },
        "enabled": True,
    },
    {
        "id": UUID("fdacccae-8954-4560-817c-331fd2fdf21c"),
        "distribution_id": "SNOWBIRD-QR-01",
        "label": "Snowbird QR - Field Check-In",
        "channel": "qr",
        "placement": "Snowbird / Little Cottonwood Canyon",
        "audience_hint": "recreation",
        "metadata_json": {
            "campaign": "snowbird",
            "form_version": 3,
            "canonical_url": "https://www.terrasatch.com/check-in",
        },
        "enabled": True,
    },
    {
        "id": UUID("4c1b30ab-9465-4b2f-9d88-a8f0ae8dc7c8"),
        "distribution_id": "UAC-EVENT-01",
        "label": "Utah Avalanche Center Event",
        "channel": "event",
        "placement": "Utah Avalanche Center event / outreach",
        "audience_hint": "both",
        "metadata_json": {
            "campaign": "uac-event",
            "form_version": 3,
            "canonical_url": "https://www.terrasatch.com/check-in",
        },
        "enabled": True,
    },
    {
        "id": UUID("1d78162b-b996-4601-b0e6-80f9b9660b11"),
        "distribution_id": "LINKEDIN-01",
        "label": "LinkedIn Check-In",
        "channel": "social",
        "placement": "LinkedIn",
        "audience_hint": "both",
        "metadata_json": {
            "campaign": "linkedin",
            "form_version": 3,
            "canonical_url": "https://www.terrasatch.com/check-in",
        },
        "enabled": True,
    },
    {
        "id": UUID("d27e3f41-c7d1-41ad-97e1-83017fc34eed"),
        "distribution_id": "BACKCOUNTRY-QR-01",
        "label": "Backcountry QR Handout",
        "channel": "qr",
        "placement": "Backcountry / general outdoor handout",
        "audience_hint": "recreation",
        "metadata_json": {
            "campaign": "backcountry",
            "form_version": 3,
            "canonical_url": "https://www.terrasatch.com/check-in",
        },
        "enabled": True,
    },
    {
        "id": UUID("9b4a2fda-1d2f-48d6-a68f-7f4534e9686d"),
        "distribution_id": "FIELD-TEAM-QR-01",
        "label": "Field Team QR Handout",
        "channel": "qr",
        "placement": "Field team / organization handout",
        "audience_hint": "work",
        "metadata_json": {
            "campaign": "field-team",
            "form_version": 3,
            "canonical_url": "https://www.terrasatch.com/check-in",
        },
        "enabled": True,
    },
)


def _distribution_table() -> sa.TableClause:
    return sa.table(
        "feedback_distributions",
        sa.column("id", sa.Uuid()),
        sa.column("distribution_id", sa.String(length=100)),
        sa.column("label", sa.String(length=255)),
        sa.column("channel", sa.String(length=32)),
        sa.column("placement", sa.String(length=255)),
        sa.column("audience_hint", sa.String(length=64)),
        sa.column("metadata_json", sa.JSON()),
        sa.column("enabled", sa.Boolean()),
    )


def upgrade() -> None:
    op.bulk_insert(_distribution_table(), list(_CAMPAIGNS))


def downgrade() -> None:
    campaign_ids = [item["distribution_id"] for item in _CAMPAIGNS]
    distributions = _distribution_table()
    op.execute(
        distributions.delete().where(distributions.c.distribution_id.in_(campaign_ids))
    )
