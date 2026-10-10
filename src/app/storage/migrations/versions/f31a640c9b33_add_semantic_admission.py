"""Add semantic admission ledger and collection status.

Revision ID: f31a640c9b33
Revises: e12a640c9b32
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f31a640c9b33"
down_revision: str | Sequence[str] | None = "e12a640c9b32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admission_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("url_canonical_hash", sa.String(64), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=True),
        sa.Column("reason", sa.String(64), nullable=True),
        sa.Column("provider_status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admission_decisions_key", "admission_decisions", ["key"], unique=True)
    op.create_index(
        "ix_admission_decisions_url_canonical_hash",
        "admission_decisions",
        ["url_canonical_hash"],
    )
    op.create_index("ix_admission_decisions_source_id", "admission_decisions", ["source_id"])
    op.create_table(
        "collection_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("collection_status")
    op.drop_table("admission_decisions")
