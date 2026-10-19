"""Add daily_signal_briefs (007 daily brief, one row per day, no FK to articles).

The table and index are created only when missing, so the upgrade also succeeds after
`create_all()` already created them (same pattern as b6d1f0a7c3e5).

Revision ID: c3a8e5d27f14
Revises: b6d1f0a7c3e5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a8e5d27f14"
down_revision: str | Sequence[str] | None = "b6d1f0a7c3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "daily_signal_briefs"
INDEX = "ix_daily_signal_briefs_report_date"


def upgrade() -> None:
    if TABLE not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("report_date", sa.Date(), nullable=False),
            sa.Column("brief_version", sa.String(64), nullable=False),
            sa.Column("model", sa.String(64), nullable=False),
            sa.Column("input_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    present = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    if INDEX not in present:
        op.create_index(INDEX, TABLE, ["report_date"], unique=True)


def downgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
