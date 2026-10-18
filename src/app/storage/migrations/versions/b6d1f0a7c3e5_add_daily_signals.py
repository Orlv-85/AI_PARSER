"""Add daily AI signals: extractions, membership, evidence, entities, overrides, reports.

Each table and index is created only when missing, so the upgrade also succeeds after
`create_all()` already created the tables (plan "Data Model + Migration").

Revision ID: b6d1f0a7c3e5
Revises: a42b750d0c44
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6d1f0a7c3e5"
down_revision: str | Sequence[str] | None = "a42b750d0c44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("article_signals", "daily_signal_scope", "signal_mentions", "ai_entities",
          "ai_entity_overrides", "daily_signal_reports")


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def _tables() -> dict[str, tuple[list, list[tuple[str, list[str], bool]]]]:
    """Table columns/constraints and (index name, columns, unique) per table."""
    return {
        "article_signals": ([
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("article_id", sa.Integer(),
                      sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("extraction_version", sa.String(64), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("reason", sa.String(255), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("retry_used", sa.Boolean(), nullable=False),
            sa.Column("event_type", sa.String(32), nullable=True),
            sa.Column("novelty_claim", sa.Boolean(), nullable=True),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("provenance", sa.Text(), nullable=False),
            _ts("created_at"), _ts("updated_at"),
            sa.UniqueConstraint("article_id", "extraction_version",
                                name="uq_article_signals_article_version"),
        ], [("ix_article_signals_article_id", ["article_id"], False),
            ("ix_article_signals_status", ["status"], False)]),
        "daily_signal_scope": ([
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scope_day", sa.Date(), nullable=False),
            sa.Column("article_id", sa.Integer(),
                      sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("publisher", sa.String(255), nullable=False),
            sa.Column("item_url", sa.String(2048), nullable=False),
            _ts("created_at"),
            sa.UniqueConstraint("scope_day", "article_id",
                                name="uq_daily_signal_scope_day_article"),
        ], [("ix_daily_signal_scope_article_id", ["article_id"], False),
            ("ix_daily_signal_scope_kind_day", ["kind", "scope_day"], False)]),
        "signal_mentions": ([
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("url_canonical_hash", sa.String(64), nullable=False),
            sa.Column("scope_day", sa.Date(), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("extraction_version", sa.String(64), nullable=False),
            sa.Column("publisher", sa.String(255), nullable=False),
            sa.Column("surface_name", sa.String(255), nullable=False),
            sa.Column("canonical_name", sa.String(255), nullable=False),
            sa.Column("name_key", sa.String(255), nullable=False),
            sa.Column("base_key", sa.String(255), nullable=False),
            sa.Column("family_key", sa.String(255), nullable=False),
            sa.Column("type_group", sa.String(16), nullable=False),
            sa.Column("entity_type", sa.String(32), nullable=False),
            sa.Column("vendor", sa.String(255), nullable=True),
            sa.Column("vendor_key", sa.String(255), nullable=False),
            sa.Column("vendor_inferred", sa.Boolean(), nullable=False),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("is_new", sa.Boolean(), nullable=False),
            sa.Column("novelty_quote", sa.String(400), nullable=True),
            sa.Column("entity_key", sa.String(300), nullable=True),
            _ts("created_at"),
            sa.UniqueConstraint("scope_day", "article_id", "url_canonical_hash",
                                "extraction_version", "name_key", "type_group",
                                name="uq_signal_mentions_identity"),
        ], [("ix_signal_mentions_scope_day", ["scope_day"], False),
            ("ix_signal_mentions_entity_key", ["entity_key"], False),
            ("ix_signal_mentions_article_hash", ["article_id", "url_canonical_hash"], False),
            ("ix_signal_mentions_group_base", ["type_group", "base_key"], False)]),
        "ai_entities": ([
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entity_key", sa.String(300), nullable=False, unique=True),
            sa.Column("display_name", sa.String(255), nullable=False),
            sa.Column("type_group", sa.String(16), nullable=False),
            sa.Column("type", sa.String(32), nullable=False),
            sa.Column("vendor", sa.String(255), nullable=True),
            sa.Column("vendor_class", sa.String(255), nullable=False),
            sa.Column("base_key", sa.String(255), nullable=False),
            sa.Column("family_key", sa.String(255), nullable=False),
            sa.Column("first_seen_day", sa.Date(), nullable=True),
            sa.Column("needs_review", sa.Boolean(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            _ts("created_at"), _ts("updated_at"),
        ], [("ix_ai_entities_first_seen_day", ["first_seen_day"], False)]),
        "ai_entity_overrides": ([
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("type_group", sa.String(16), nullable=False),
            sa.Column("match_key", sa.String(255), nullable=False),
            sa.Column("vendor_class", sa.String(255), nullable=False),
            sa.Column("target_base_key", sa.String(255), nullable=False),
            sa.Column("target_vendor_class", sa.String(255), nullable=False),
            sa.Column("target_entity_key", sa.String(300), nullable=False),
            sa.Column("note", sa.String(255), nullable=True),
            _ts("created_at"),
            sa.UniqueConstraint("kind", "type_group", "match_key", "vendor_class",
                                name="uq_ai_entity_overrides_selector"),
        ], [("ix_ai_entity_overrides_kind", ["kind"], False)]),
        "daily_signal_reports": ([
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("report_date", sa.Date(), nullable=False),
            sa.Column("methodology_version", sa.String(64), nullable=False),
            sa.Column("extraction_version", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("thresholds", sa.Text(), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("coverage", sa.Text(), nullable=False),
            _ts("created_at"), _ts("updated_at"),
        ], [("ix_daily_signal_reports_report_date", ["report_date"], True)]),
    }


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    for name, (columns, indexes) in _tables().items():
        if name not in existing:
            op.create_table(name, *columns)
        present = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(name)}
        for index_name, index_columns, unique in indexes:
            if index_name not in present:
                op.create_index(index_name, name, index_columns, unique=unique)


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for name in reversed(TABLES):
        if name in existing:
            op.drop_table(name)
