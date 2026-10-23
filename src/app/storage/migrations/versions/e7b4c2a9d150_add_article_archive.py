"""Add archive_documents and archive_texts (016 article archive, no FK to articles or sources).

Tables and indexes are created only when missing, so the upgrade also succeeds after
`create_all()` already created them (same pattern as c3a8e5d27f14).

Revision ID: e7b4c2a9d150
Revises: c3a8e5d27f14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b4c2a9d150"
down_revision: str | Sequence[str] | None = "c3a8e5d27f14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENTS = "archive_documents"
TEXTS = "archive_texts"
INDEXES = (
    (DOCUMENTS, "ix_archive_documents_url_canonical_hash", ["url_canonical_hash"], True),
    (DOCUMENTS, "ix_archive_documents_host", ["host"], False),
    (DOCUMENTS, "ix_archive_documents_article_id", ["article_id"], False),
    (DOCUMENTS, "ix_archive_documents_state", ["state"], False),
    (TEXTS, "ix_archive_texts_document_id", ["document_id"], False),
)


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if DOCUMENTS not in tables:
        op.create_table(
            DOCUMENTS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("url_canonical_hash", sa.String(64), nullable=False),
            sa.Column("url", sa.String(2048), nullable=False),
            sa.Column("url_canonical", sa.String(2048), nullable=False),
            sa.Column("source_key", sa.String(64), nullable=True),
            sa.Column("host", sa.String(255), nullable=False),
            sa.Column("title", sa.String(512), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("publication_day", sa.Date(), nullable=True),
            sa.Column("publication_status", sa.String(32), nullable=True),
            sa.Column("article_id", sa.Integer(), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_issue", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    if TEXTS not in tables:
        op.create_table(
            TEXTS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey(f"{DOCUMENTS}.id"),
                      nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("text_chars", sa.Integer(), nullable=False),
            sa.Column("text_sha256", sa.String(64), nullable=False),
            sa.Column("origin", sa.String(32), nullable=False),
            sa.Column("extraction_version", sa.String(64), nullable=False),
            sa.Column("final_url", sa.String(2048), nullable=True),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("issues", sa.Text(), nullable=False),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("document_id", "text_sha256", name="uq_archive_texts_document_sha"))
    for table, name, columns, unique in INDEXES:
        present = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
        if name not in present:
            op.create_index(name, table, columns, unique=unique)


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in (TEXTS, DOCUMENTS):
        if table in tables:
            op.drop_table(table)
