"""Add kind and kind_confidence to world_change_assessments (018 selection, world-change-2).

Both columns are nullable: rows of `world-change-1` keep NULL. A column is added only when
missing, so the upgrade also succeeds after `create_all()` already made it.

Revision ID: d7f3a9b25c61
Revises: a6b0180c0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f3a9b25c61"
down_revision: str | Sequence[str] | None = "a6b0180c0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "world_change_assessments"


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    present = _columns()
    with op.batch_alter_table(TABLE) as batch:
        if "kind" not in present:
            batch.add_column(sa.Column("kind", sa.String(16), nullable=True))
        if "kind_confidence" not in present:
            batch.add_column(sa.Column("kind_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    present = _columns()
    with op.batch_alter_table(TABLE) as batch:
        if "kind_confidence" in present:
            batch.drop_column("kind_confidence")
        if "kind" in present:
            batch.drop_column("kind")
