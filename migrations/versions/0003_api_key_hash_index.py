"""Index API-key secret hashes.

Revision ID: 0003_api_key_hash_index
Revises: 0002_tenant_identity
Create Date: 2026-08-11 00:10:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_api_key_hash_index"
down_revision: str | None = "0002_tenant_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_api_keys_secret_hash", "api_keys", ["secret_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_api_keys_secret_hash", "api_keys", type_="unique")