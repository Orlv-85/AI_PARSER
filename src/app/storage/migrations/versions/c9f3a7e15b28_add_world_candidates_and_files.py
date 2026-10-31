"""Add world_candidates and world_files (018 world news stream, no FK to articles).

Tables and indexes are created only when missing, so the upgrade also succeeds after
`create_all()` already created them (same pattern as e7b4c2a9d150).

Revision ID: c9f3a7e15b28
Revises: b8e2d4f61a07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9f3a7e15b28"
down_revision: str | Sequence[str] | None = "b8e2d4f61a07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANDIDATES = "world_candidates"
FILES = "world_files"
INDEXES = (
    (CANDIDATES, "ix_world_candidates_url_canonical_hash", ["url_canonical_hash"], True),
    (CANDIDATES, "ix_world_candidates_first_seen_at", ["first_seen_at"], False),
    (CANDIDATES, "ix_world_candidates_cluster_key", ["cluster_key"], False),
    (CANDIDATES, "ix_world_candidates_state", ["state"], False),
)


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if CANDIDATES not in tables:
        op.create_table(
            CANDIDATES,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("url_canonical_hash", sa.String(64), nullable=False),
            sa.Column("url", sa.String(2048), nullable=False),
            sa.Column("title", sa.String(512), nullable=False),
            sa.Column("source_domain", sa.String(255), nullable=False),
            sa.Column("language", sa.String(16), nullable=False),
            sa.Column("country_hint", sa.String(8), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("gdelt_file", sa.String(64), nullable=False),
            sa.Column("match_kind", sa.String(16), nullable=False),
            sa.Column("cluster_key", sa.String(64), nullable=False),
            sa.Column("priority", sa.Float(), nullable=True),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("screen_confidence", sa.Float(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("last_error", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    if FILES not in tables:
        op.create_table(
            FILES,
            sa.Column("stamp", sa.String(14), primary_key=True),
            sa.Column("kind", sa.String(16), primary_key=True),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("rows", sa.Integer(), nullable=False),
            sa.Column("matched", sa.Integer(), nullable=False),
            sa.Column("error", sa.String(255), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    for table, name, columns, unique in INDEXES:
        present = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
        if name not in present:
            op.create_index(name, table, columns, unique=unique)


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in (FILES, CANDIDATES):
        if table in tables:
            op.drop_table(table)
