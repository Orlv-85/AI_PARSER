"""Anonymous page views (018 item 6b); behavior: src/app/web/pages.md.

Revision ID: a6b0180c0001
Revises: d2a6f8b03c19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6b0180c0001"
down_revision: str | Sequence[str] | None = "d2a6f8b03c19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "page_views"


def upgrade() -> None:
    if TABLE not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            TABLE,
            sa.Column("day", sa.Date(), primary_key=True),
            sa.Column("route", sa.Text(), primary_key=True),
            sa.Column("count", sa.Integer(), nullable=False))


def downgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
