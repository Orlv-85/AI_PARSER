"""Add bulletins, creating only when missing (018 item 4a).

Revision ID: d2a6f8b03c19
Revises: c9f3a7e15b28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2a6f8b03c19"
down_revision: str | Sequence[str] | None = "c9f3a7e15b28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "bulletins"


def upgrade() -> None:
    if TABLE not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            TABLE,
            sa.Column("day", sa.Date(), primary_key=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("numbers", sa.JSON(), nullable=False),
            sa.Column("versions", sa.JSON(), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("telegram_message_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
