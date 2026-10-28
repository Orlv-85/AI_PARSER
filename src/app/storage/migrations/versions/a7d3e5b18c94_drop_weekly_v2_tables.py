"""Drop the eight weekly v2 tables (017 T041).

Upgrade drops them with IF EXISTS in FK-safe order (their indexes go with the tables).
Downgrade recreates them empty, copied from e12a640c9b32 (the model classes are gone).

Revision ID: a7d3e5b18c94
Revises: f4a9c1d27b83
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3e5b18c94"
down_revision: str | Sequence[str] | None = "f4a9c1d27b83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Children first: weekly_publications has an FK to weekly_snapshots.
DROP_ORDER = ("weekly_publications", "weekly_snapshots", "weekly_jobs", "weekly_topic_versions",
              "weekly_decisions", "weekly_input_observations", "weekly_coverage_attempts",
              "weekly_source_versions")


def upgrade() -> None:
    for table in DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    create = {
        "weekly_source_versions": lambda: op.create_table(
            "weekly_source_versions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("publisher", sa.String(255), nullable=False),
            sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("interval_minutes", sa.Integer(), nullable=False),
            sa.Column("configuration", sa.Text(), nullable=False),
        ),
        "weekly_coverage_attempts": lambda: op.create_table(
            "weekly_coverage_attempts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.String(64), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("version_id", sa.String(64), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("outcome", sa.String(32), nullable=False),
            sa.Column("complete", sa.Boolean(), nullable=False),
            sa.Column("expected_attempts", sa.Integer(), nullable=False),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("run_id", "source_id"),
        ),
        "weekly_input_observations": lambda: op.create_table(
            "weekly_input_observations",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("canonical_hash", sa.String(64), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
        ),
        "weekly_decisions": lambda: op.create_table(
            "weekly_decisions",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("task", sa.String(32), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        ),
        "weekly_topic_versions": lambda: op.create_table(
            "weekly_topic_versions",
            sa.Column("id", sa.String(128), primary_key=True),
            sa.Column("taxonomy_version", sa.String(64), nullable=False),
            sa.Column("topic_id", sa.String(64), nullable=False),
            sa.Column("definition", sa.Text(), nullable=False),
            sa.UniqueConstraint("taxonomy_version", "topic_id"),
        ),
        "weekly_jobs": lambda: op.create_table(
            "weekly_jobs",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("report_date", sa.Date(), nullable=False),
            sa.Column("methodology_version", sa.String(64), nullable=False),
            sa.Column("input_fingerprint", sa.String(64), nullable=False),
            sa.Column("input_payload", sa.Text(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("lease_token", sa.String(64), nullable=True),
            sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("error", sa.String(255), nullable=True),
        ),
        "weekly_snapshots": lambda: op.create_table(
            "weekly_snapshots",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("report_date", sa.Date(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.UniqueConstraint("report_date", "revision"),
        ),
        "weekly_publications": lambda: op.create_table(
            "weekly_publications",
            sa.Column("report_date", sa.Date(), primary_key=True),
            sa.Column("snapshot_id", sa.String(64), sa.ForeignKey("weekly_snapshots.id"),
                      nullable=True),
        ),
    }
    for table in reversed(DROP_ORDER):
        if table not in tables:
            create[table]()
    indexed = {
        "weekly_source_versions": ["source_id", "publisher"],
        "weekly_coverage_attempts": ["source_id", "version_id", "day"],
        "weekly_input_observations": ["source_id", "canonical_hash", "published_at"],
        "weekly_decisions": ["task"], "weekly_jobs": ["report_date", "status"],
        "weekly_snapshots": ["report_date"],
    }
    for table, columns in indexed.items():
        if table in tables:
            continue
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
