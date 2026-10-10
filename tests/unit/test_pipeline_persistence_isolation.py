from datetime import UTC, datetime
from logging import getLogger
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.models import Article
from app.core.pipeline import HtmlLinkFetchResult, run_fetch_cycle
from app.storage.models_sql import Article as StoredArticle
from app.storage.models_sql import Base, Source
from app.storage.repos import ArticleRepo


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("source_type", ["rss", "html"])
def test_source_savepoint_recovers_after_database_error(
    monkeypatch, tmp_path, caplog, batch, source_type,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/isolation.db")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TRIGGER reject_article BEFORE INSERT ON articles "
            "WHEN NEW.title = 'Invalid' BEGIN SELECT RAISE(ABORT, 'invalid article'); END"
        ))
    sessions = sessionmaker(bind=engine, autoflush=False)
    configs = [
        SourceConfig(
            id=key, name=key, type=source_type, url=f"https://example.com/{key}",
            html={} if source_type == "html" else None,
        )
        for key in ("before", "broken", "after")
    ]
    now = datetime(2026, 10, 4, 12, tzinfo=UTC)
    articles = {
        key: [Article(
            source_key=key, title="AI update", url=f"https://example.com/{key}/1",
            published_at=now,
        )]
        for key in ("before", "broken", "after")
    }
    articles["broken"].append(Article(
        source_key="broken", title="Invalid", url="https://example.com/broken/2",
        published_at=now,
    ))

    def collect(**_kwargs):
        results = {}
        for index, config in enumerate(configs):
            items = articles[config.id]
            if source_type == "html":
                results[index] = HtmlLinkFetchResult(
                    links=[str(item.url) for item in items], etag="new-validator",
                )
            else:
                results[index] = SimpleNamespace(items=items, etag="new-validator")
        return results, 0

    def fetch_article(*, source, url, **_kwargs):
        return next(item for item in articles[source.id] if str(item.url) == url)

    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: configs)
    monkeypatch.setattr("app.core.pipeline.create_all", lambda: None)
    monkeypatch.setattr("app.core.pipeline.SessionLocal", sessions)
    monkeypatch.setattr("app.core.pipeline._collect_fetched_items", collect)
    monkeypatch.setattr("app.core.pipeline.fetch_html_article", fetch_article)
    settings = Settings(
        article_batch_upsert_enabled=batch, respect_robots_txt=False,
        rss_known_streak_stop=0,
    )
    logger = getLogger("persistence-isolation")

    summary = run_fetch_cycle(settings=settings, logger=logger)

    assert summary.errors == 1
    assert summary.new == 2
    assert summary.duplicates == 0
    with sessions() as session:
        assert set(session.scalars(select(StoredArticle.url))) == {
            "https://example.com/before/1", "https://example.com/after/1",
        }
        sources = {source.source_key: source for source in session.scalars(select(Source))}
        assert sources["before"].etag == "new-validator"
        assert sources["after"].etag == "new-validator"
        assert sources["broken"].etag is None
        assert sources["broken"].last_checked_at is None
    failure = next(record for record in caplog.records if record.msg == "source_persist_failed")
    assert failure.args["source_id"] == "broken"
    assert failure.args["stage"] == "persist"

    articles["broken"][1] = articles["broken"][1].model_copy(update={"title": "Recovered"})
    recovered = run_fetch_cycle(settings=settings, logger=logger)
    assert recovered.errors == 0
    assert recovered.new == 2
    assert recovered.duplicates == 2
    with sessions() as session:
        assert len(list(session.scalars(select(StoredArticle)))) == 4
        source = session.scalar(select(Source).where(Source.source_key == "broken"))
        assert source is not None
        assert source.etag == "new-validator"


@pytest.mark.parametrize("batch", [False, True])
def test_article_storage_bounds_long_titles_in_both_insert_modes(tmp_path, batch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/titles.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    title = "AI headline " * 100
    row = {
        "source_id": None, "title": title, "url": "https://example.com/story",
        "url_canonical": "https://example.com/story", "url_canonical_hash": "title-test",
        "published_at": datetime.now(UTC), "ai_relevance_score": 0.5,
        "freshness_score": 0.5, "rank_score": 0.5,
    }
    with sessions() as session:
        repo = ArticleRepo(session)
        if batch:
            assert repo.upsert_articles_batch([row]) == (1, 0)
        else:
            _, is_new = repo.insert_article(**row)
            assert is_new
        session.commit()
    with sessions() as session:
        stored = session.scalar(select(StoredArticle))
        assert stored is not None
        assert stored.title == title[:512]
    assert row["title"] == title
