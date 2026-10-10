"""Add weekly attention evidence, coverage, caches, jobs and revisions.

Revision ID: e12a640c9b32
Revises: c9e71b82a640
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e12a640c9b32"
down_revision: str | Sequence[str] | None = "c9e71b82a640"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weekly_source_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("publisher", sa.String(255), nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("configuration", sa.Text(), nullable=False),
    )
    op.create_table(
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
    )
    op.create_table(
        "weekly_input_observations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("canonical_hash", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_table(
        "weekly_decisions",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("task", sa.String(32), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "weekly_topic_versions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("taxonomy_version", sa.String(64), nullable=False),
        sa.Column("topic_id", sa.String(64), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.UniqueConstraint("taxonomy_version", "topic_id"),
    )
    op.create_table(
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
    )
    op.create_table(
        "weekly_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.UniqueConstraint("report_date", "revision"),
    )
    op.create_table(
        "weekly_publications",
        sa.Column("report_date", sa.Date(), primary_key=True),
        sa.Column("snapshot_id", sa.String(64), sa.ForeignKey("weekly_snapshots.id"),
                  nullable=True),
    )
    for table, columns in {
        "weekly_source_versions": ["source_id", "publisher"],
        "weekly_coverage_attempts": ["source_id", "version_id", "day"],
        "weekly_input_observations": ["source_id", "canonical_hash", "published_at"],
        "weekly_decisions": ["task"], "weekly_jobs": ["report_date", "status"],
        "weekly_snapshots": ["report_date"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in ("weekly_publications", "weekly_snapshots", "weekly_jobs",
                  "weekly_topic_versions", "weekly_decisions", "weekly_input_observations",
                  "weekly_coverage_attempts", "weekly_source_versions"):
        op.drop_table(table)
