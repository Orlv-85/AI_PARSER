from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.sources import SourceConfig
from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.models import Article
from app.core.scoring import ai_relevance_score, freshness_score, rank_score
from app.ingest.html import extract_article_text, extract_links_from_html
from app.ingest.rss import parse_rss
from app.storage.models_sql import Base
from app.storage.repos import ArticleRepo, SourceRepo


def _build_test_articles() -> list[Article]:
    rss_fixture = Path("tests/fixtures/rss/sample_feed.xml").read_bytes()
    rss_items = parse_rss(source_key="rss_source", content=rss_fixture)

    list_html = Path("tests/fixtures/html/list_page.html").read_text(encoding="utf-8")
    article_html = Path("tests/fixtures/html/article_page.html").read_text(encoding="utf-8")
    html_links = extract_links_from_html(
        html_content=list_html,
        base_url="https://example.com",
        list_selector="main.news-list",
        link_selector="a",
    )
    html_content = extract_article_text(
        html_content=article_html,
        url="https://example.com/news/post-1",
        strategy="readability",
    )
    html_items = [
        Article(
            source_key="html_source",
            title="AI Safety Update",
            url=html_links[0],
            published_at=datetime(2026, 2, 21, 11, 0, tzinfo=UTC),
            summary=None,
            content=html_content,
        )
    ]
    return rss_items + html_items


def test_ingest_persist_query_pipeline_is_deterministic() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    now = datetime(2026, 2, 21, 12, 0, tzinfo=UTC)

    with session_local() as session:
        source_repo = SourceRepo(session)
        article_repo = ArticleRepo(session)

        source_repo.upsert_source(
            SourceConfig(
                id="rss_source",
                name="RSS Source",
                type="rss",
                url="https://example.com/feed.xml",
                enabled=True,
                fetch_interval_minutes=30,
                source_weight=1.0,
            )
        )
        html_source = source_repo.upsert_source(
            SourceConfig(
                id="html_source",
                name="HTML Source",
                type="html",
                url="https://example.com/news",
                enabled=True,
                fetch_interval_minutes=30,
                source_weight=0.9,
                html={
                    "list_selector": "main.news-list",
                    "link_selector": "a",
                    "article_selector": "article",
                    "extraction_strategy": "readability",
                },
            )
        )

        articles = _build_test_articles()
        inserted_ids: list[int] = []
        for item in articles:
            canonical = canonicalize_url(str(item.url))
            canonical_hash = canonical_url_hash(str(item.url))
            relevance = ai_relevance_score(item)
            freshness = freshness_score(item.published_at, now=now)
            score = rank_score(relevance=relevance, freshness=freshness, source_weight=0.9)

            source_id = html_source.id if item.source_key == "html_source" else None
            saved, is_new = article_repo.insert_article(
                source_id=source_id,
                title=item.title,
                url=str(item.url),
                url_canonical=canonical,
                url_canonical_hash=canonical_hash,
                published_at=item.published_at or (now - timedelta(hours=1)),
                summary=item.summary,
                content=item.content,
                ai_relevance_score=relevance,
                freshness_score=freshness,
                rank_score=score,
            )
            if is_new:
                inserted_ids.append(saved.id)

        # Duplicate pass should not create extra rows.
        duplicate_item = articles[0]
        _, is_new = article_repo.insert_article(
            source_id=None,
            title=duplicate_item.title,
            url=str(duplicate_item.url),
            url_canonical=canonicalize_url(str(duplicate_item.url)),
            url_canonical_hash=canonical_url_hash(str(duplicate_item.url)),
            published_at=duplicate_item.published_at or now,
            summary=duplicate_item.summary,
            content=duplicate_item.content,
            ai_relevance_score=0.5,
            freshness_score=0.5,
            rank_score=0.5,
        )
        session.commit()

        assert is_new is False
        top = article_repo.query_top(hours=24, limit=10)
        assert len(top) == len(inserted_ids)
        assert top == sorted(top, key=lambda row: (row.rank_score, row.published_at), reverse=True)
        assert len(top) > 0
