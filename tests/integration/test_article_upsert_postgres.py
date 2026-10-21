import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.storage.article_repo import ArticleRepo
from app.storage.models_sql import Article, Base

POSTGRES_TEST_URL = os.getenv("AINEWS_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="AINEWS_TEST_POSTGRES_URL is not set",
)


def test_upsert_articles_batch_uses_postgres_on_conflict_round_trip() -> None:
    # Own schema so parallel xdist workers never share tables.
    schema = "upsert_" + uuid4().hex
    admin = create_engine(str(POSTGRES_TEST_URL), future=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        str(POSTGRES_TEST_URL), future=True, connect_args={"options": "-csearch_path=" + schema}
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    now = datetime(2026, 2, 24, 13, 0, tzinfo=UTC)

    with session_local() as session:
        article_repo = ArticleRepo(session)
        article_repo.upsert_articles_batch(
            [
                {
                    "source_id": None,
                    "title": "Original",
                    "url": "https://example.com/item",
                    "url_canonical": "https://example.com/item",
                    "url_canonical_hash": "h-item",
                    "published_at": now,
                    "summary": "old",
                    "content": "old",
                    "ai_relevance_score": 0.1,
                    "freshness_score": 0.1,
                    "rank_score": 0.1,
                }
            ]
        )
        new_count, duplicate_count = article_repo.upsert_articles_batch(
            [
                {
                    "source_id": None,
                    "title": "Updated",
                    "url": "https://example.com/item",
                    "url_canonical": "https://example.com/item",
                    "url_canonical_hash": "h-item",
                    "published_at": now,
                    "summary": "new",
                    "content": "new",
                    "ai_relevance_score": 0.9,
                    "freshness_score": 0.9,
                    "rank_score": 0.9,
                }
            ]
        )
        session.commit()

        row = session.execute(
            select(Article).where(Article.url_canonical_hash == "h-item")
        ).scalar_one()
        assert new_count == 0
        assert duplicate_count == 1
        assert row.title == "Original"
        assert row.summary == "old"
        assert row.ai_relevance_score == 0.9
        assert row.rank_score == 0.9
