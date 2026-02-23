"""add source fetch state columns

Revision ID: 5f3c9f6f2a11
Revises: d5686ed0fc60
Create Date: 2026-02-23 23:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f3c9f6f2a11"
down_revision: str | Sequence[str] | None = "d5686ed0fc60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sources", sa.Column("etag", sa.String(length=512), nullable=True))
    op.add_column("sources", sa.Column("last_modified", sa.String(length=256), nullable=True))
    op.add_column(
        "sources",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("sources", sa.Column("last_status_code", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sources", "last_status_code")
    op.drop_column("sources", "last_checked_at")
    op.drop_column("sources", "last_modified")
    op.drop_column("sources", "etag")
