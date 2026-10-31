"""Add world_change_assessments (018 Jev world_change answers, no FK to articles).

The table and its indexes are created only when missing, so the upgrade also succeeds after
`create_all()` already created them (same pattern as e7b4c2a9d150).

Revision ID: b8e2d4f61a07
Revises: a7d3e5b18c94
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e2d4f61a07"
down_revision: str | Sequence[str] | None = "a7d3e5b18c94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "world_change_assessments"
INDEX = "ix_world_change_assessments_url_canonical_hash"


def upgrade() -> None:
    if TABLE not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("url_canonical_hash", sa.String(64), nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=True),
            sa.Column("world_change", sa.String(16), nullable=False),
            sa.Column("world_change_confidence", sa.Float(), nullable=False),
            sa.Column("area", sa.String(16), nullable=False),
            sa.Column("area_confidence", sa.Float(), nullable=False),
            sa.Column("actor", sa.String(16), nullable=False),
            sa.Column("actor_confidence", sa.Float(), nullable=False),
            sa.Column("harm_to_people", sa.Float(), nullable=False),
            sa.Column("question_version", sa.String(64), nullable=False),
            sa.Column("model", sa.String(64), nullable=False),
            sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("url_canonical_hash", "question_version",
                                name="uq_world_change_hash_version"))
    present = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    if INDEX not in present:
        op.create_index(INDEX, TABLE, ["url_canonical_hash"])


def downgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
