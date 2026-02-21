from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.sources import SourceConfig
from app.storage import db
from app.storage.models_sql import Base
from app.storage.repos import ArticleRepo, SourceRepo


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_build_engine_uses_settings_database_url(monkeypatch) -> None:
    class _Settings:
        database_url = "sqlite:///:memory:"

    captured: dict[str, object] = {}

    def _fake_create_engine(url: str, future: bool):
        captured["url"] = url
        captured["future"] = future
        return "engine"

    def _fake_get_settings():
        return _Settings()

    monkeypatch.setattr("app.storage.db.get_settings", _fake_get_settings)
    monkeypatch.setattr("app.storage.db.create_engine", _fake_create_engine)

    assert db.build_engine() == "engine"
    assert captured == {"url": "sqlite:///:memory:", "future": True}


def test_create_all_and_get_session(monkeypatch) -> None:
    called: dict[str, object] = {}

    monkeypatch.setattr(
        "app.storage.db.Base.metadata.create_all",
        lambda bind: called.setdefault("bind", bind),
    )
    monkeypatch.setattr("app.storage.db.engine", "test-engine")
    db.create_all()
    assert called["bind"] == "test-engine"

    class _Session:
        def __init__(self):
            self.closed = False

        def close(self) -> None:
            self.closed = True

    session = _Session()
    monkeypatch.setattr("app.storage.db.SessionLocal", lambda: session)

    gen = db.get_session()
    yielded = next(gen)
    assert yielded is session
    try:
        next(gen)
    except StopIteration:
        pass

    assert session.closed is True


def test_source_repo_and_article_repo_paths() -> None:
    session = _session()
    source_repo = SourceRepo(session)
    article_repo = ArticleRepo(session)

    source_cfg = SourceConfig(
        id="source_1",
        name="Source",
        type="rss",
        url="https://example.com/feed",
        enabled=True,
    )
    source = source_repo.upsert_source(source_cfg)
    source_updated = source_repo.upsert_source(
        SourceConfig(
            id="source_1",
            name="Source Updated",
            type="rss",
            url="https://example.com/feed",
            enabled=True,
        )
    )
    assert source_updated.id == source.id
    assert source_updated.name == "Source Updated"

    source_repo.upsert_source(
        SourceConfig(
            id="source_2",
            name="Disabled",
            type="rss",
            url="https://example.com/disabled",
            enabled=False,
        )
    )
    enabled = source_repo.list_enabled_sources()
    assert [row.source_key for row in enabled] == ["source_1"]

    now = datetime.now(UTC)
    article, is_new = article_repo.insert_article(
        source_id=source.id,
        title="A",
        url="https://example.com/a",
        url_canonical="https://example.com/a",
        url_canonical_hash="h1",
        published_at=now,
    )
    assert is_new is True

    same, is_new_again = article_repo.insert_article(
        source_id=source.id,
        title="A2",
        url="https://example.com/a2",
        url_canonical="https://example.com/a",
        url_canonical_hash="h1",
        published_at=now,
    )
    assert is_new_again is False
    assert same.id == article.id

    alias = article_repo.add_alias(article_id=article.id, source_id=source.id, url="https://alt")
    alias2 = article_repo.merge_alias(
        existing_article_id=article.id,
        source_id=source.id,
        url="https://alt2",
    )
    assert alias.article_id == article.id
    assert alias2.url == "https://alt2"

    old_time = now - timedelta(days=10)
    article_repo.insert_article(
        source_id=source.id,
        title="Old",
        url="https://example.com/old",
        url_canonical="https://example.com/old",
        url_canonical_hash="h2",
        published_at=old_time,
        summary="legacy",
        content="legacy",
    )

    recent_results = article_repo.query_top(hours=24, limit=10)
    assert [row.title for row in recent_results] == ["A"]

    found = article_repo.search(query="leg", days=30, limit=10)
    assert [row.title for row in found] == ["Old"]


def test_list_for_view_applies_sort_with_query() -> None:
    session = _session()
    article_repo = ArticleRepo(session)
    now = datetime.now(UTC)

    article_repo.insert_article(
        source_id=None,
        title="AI Recent Lower Rank",
        url="https://example.com/recent",
        url_canonical="https://example.com/recent",
        url_canonical_hash="q1",
        published_at=now - timedelta(hours=1),
        summary="ai summary",
        content="ai content",
        rank_score=0.2,
    )
    article_repo.insert_article(
        source_id=None,
        title="AI Older Higher Rank",
        url="https://example.com/older",
        url_canonical="https://example.com/older",
        url_canonical_hash="q2",
        published_at=now - timedelta(hours=2),
        summary="ai summary",
        content="ai content",
        rank_score=0.9,
    )

    by_rank = article_repo.list_for_view(
        hours=24,
        limit=10,
        query="ai",
        days=7,
        sort="rank",
    )
    by_published = article_repo.list_for_view(
        hours=24,
        limit=10,
        query="ai",
        days=7,
        sort="published",
    )

    assert [row[0].title for row in by_rank] == [
        "AI Older Higher Rank",
        "AI Recent Lower Rank",
    ]
    assert [row[0].title for row in by_published] == [
        "AI Recent Lower Rank",
        "AI Older Higher Rank",
    ]
