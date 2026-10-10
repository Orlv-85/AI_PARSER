"""Add persisted article categories and confidence.

Revision ID: c9e71b82a640
Revises: 8b3a2d4e9f10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e71b82a640"
down_revision: str | Sequence[str] | None = "8b3a2d4e9f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("category", sa.String(64), nullable=True))
    op.add_column("articles", sa.Column("category_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "category_confidence")
    op.drop_column("articles", "category")
