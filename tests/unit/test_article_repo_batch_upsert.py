from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models_sql import Article, Base
from app.storage.repos import ArticleRepo


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_upsert_articles_batch_counts_new_and_duplicates_and_updates_existing() -> None:
    session = _session()
    article_repo = ArticleRepo(session)
    now = datetime(2026, 2, 24, 12, 0, tzinfo=UTC)

    article_repo.insert_article(
        source_id=None,
        title="Existing",
        url="https://example.com/existing",
        url_canonical="https://example.com/existing",
        url_canonical_hash="h-existing",
        published_at=now,
        summary="old",
        content="old-content",
        ai_relevance_score=0.1,
        freshness_score=0.1,
        rank_score=0.1,
    )

    new_count, duplicate_count = article_repo.upsert_articles_batch(
        [
            {
                "source_id": None,
                "title": "Existing Updated",
                "url": "https://example.com/existing",
                "url_canonical": "https://example.com/existing",
                "url_canonical_hash": "h-existing",
                "published_at": now,
                "summary": "new",
                "content": "new-content",
                "ai_relevance_score": 0.9,
                "freshness_score": 0.8,
                "rank_score": 0.7,
            },
            {
                "source_id": None,
                "title": "Fresh One",
                "url": "https://example.com/fresh",
                "url_canonical": "https://example.com/fresh",
                "url_canonical_hash": "h-fresh",
                "published_at": now,
                "summary": None,
                "content": None,
                "ai_relevance_score": 0.5,
                "freshness_score": 0.5,
                "rank_score": 0.5,
            },
            {
                "source_id": None,
                "title": "Fresh One Latest",
                "url": "https://example.com/fresh",
                "url_canonical": "https://example.com/fresh",
                "url_canonical_hash": "h-fresh",
                "published_at": now,
                "summary": "latest",
                "content": "latest-content",
                "ai_relevance_score": 0.6,
                "freshness_score": 0.6,
                "rank_score": 0.6,
            },
        ]
    )
    session.commit()

    assert new_count == 1
    assert duplicate_count == 2

    rows = (
        session.query(Article)
        .order_by(Article.url_canonical_hash.asc())
        .all()
    )
    assert [row.url_canonical_hash for row in rows] == ["h-existing", "h-fresh"]
    existing, fresh = rows
    assert existing.title == "Existing"
    assert existing.summary == "old"
    assert existing.ai_relevance_score == 0.9
    assert existing.rank_score == 0.7
    assert fresh.title == "Fresh One"
    assert fresh.summary is None
    assert fresh.content is None
    assert fresh.ai_relevance_score == 0.6
    assert fresh.rank_score == 0.6


def test_upsert_articles_batch_empty_input_is_noop() -> None:
    session = _session()
    article_repo = ArticleRepo(session)

    assert article_repo.upsert_articles_batch([]) == (0, 0)
