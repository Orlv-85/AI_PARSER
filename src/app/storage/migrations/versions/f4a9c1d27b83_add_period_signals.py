"""Add period_signal_reports and period_signal_briefs (017 weekly and monthly signals).

No foreign keys. Tables and indexes are created only when missing, so the upgrade also succeeds
after `create_all()` already created them (same pattern as e7b4c2a9d150).

Revision ID: f4a9c1d27b83
Revises: e7b4c2a9d150
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a9c1d27b83"
down_revision: str | Sequence[str] | None = "e7b4c2a9d150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REPORTS = "period_signal_reports"
BRIEFS = "period_signal_briefs"


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if REPORTS not in tables:
        op.create_table(
            REPORTS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("period_kind", sa.String(16), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("methodology_version", sa.String(64), nullable=False),
            sa.Column("extraction_version", sa.String(64), nullable=False),
            sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("thresholds", sa.Text(), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("coverage", sa.Text(), nullable=False),
            _ts("created_at"), _ts("updated_at"),
            sa.UniqueConstraint("period_kind", "period_start",
                                name="uq_period_signal_reports_kind_start"))
    if BRIEFS not in tables:
        op.create_table(
            BRIEFS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("period_kind", sa.String(16), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("brief_version", sa.String(64), nullable=False),
            sa.Column("model", sa.String(64), nullable=False),
            sa.Column("input_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("payload", sa.Text(), nullable=False),
            _ts("created_at"), _ts("updated_at"),
            sa.UniqueConstraint("period_kind", "period_start",
                                name="uq_period_signal_briefs_kind_start"))


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in (BRIEFS, REPORTS):
        if table in tables:
            op.drop_table(table)
