"""add weekly analytics report tables

Revision ID: 8b3a2d4e9f10
Revises: 5f3c9f6f2a11
Create Date: 2026-03-14 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b3a2d4e9f10"
down_revision: str | Sequence[str] | None = "5f3c9f6f2a11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "weekly_analytics_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_weekly_analytics_reports_report_date"),
        "weekly_analytics_reports",
        ["report_date"],
        unique=True,
    )
    op.create_table(
        "weekly_analytics_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("section_name", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["weekly_analytics_reports.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_weekly_analytics_items_report_id"),
        "weekly_analytics_items",
        ["report_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_weekly_analytics_items_section_name"),
        "weekly_analytics_items",
        ["section_name"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_weekly_analytics_items_section_name"),
        table_name="weekly_analytics_items",
    )
    op.drop_index(op.f("ix_weekly_analytics_items_report_id"), table_name="weekly_analytics_items")
    op.drop_table("weekly_analytics_items")
    op.drop_index(
        op.f("ix_weekly_analytics_reports_report_date"),
        table_name="weekly_analytics_reports",
    )
    op.drop_table("weekly_analytics_reports")
