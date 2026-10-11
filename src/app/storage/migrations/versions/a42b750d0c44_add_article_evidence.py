"""Separate unknown publication dates and persist re-enrichment provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a42b750d0c44"
down_revision: str | Sequence[str] | None = "f31a640c9b33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("articles") as batch:
        batch.alter_column("published_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch.add_column(sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("publication_day", sa.Date(), nullable=True))
        batch.add_column(
            sa.Column(
                "publication_status",
                sa.String(32),
                nullable=False,
                server_default="legacy_unverified",
            )
        )
        batch.add_column(sa.Column("publication_precision", sa.String(32), nullable=True))
        batch.add_column(sa.Column("date_provenance", sa.Text(), nullable=True))
        batch.add_column(sa.Column("enrichment_provenance", sa.Text(), nullable=True))
        batch.add_column(sa.Column("material_type", sa.String(32), nullable=True))
        batch.add_column(sa.Column("compared_products", sa.Text(), nullable=True))
        batch.create_index("ix_articles_publication_day", ["publication_day"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM articles WHERE published_at IS NULL")).scalar():
        raise RuntimeError("Cannot downgrade unknown publication dates without inventing dates")
    with op.batch_alter_table("articles") as batch:
        batch.drop_index("ix_articles_publication_day")
        for name in (
            "compared_products",
            "material_type",
            "enrichment_provenance",
            "date_provenance",
            "publication_precision",
            "publication_status",
            "modified_at",
            "publication_day",
        ):
            batch.drop_column(name)
        batch.alter_column("published_at", existing_type=sa.DateTime(timezone=True), nullable=False)
