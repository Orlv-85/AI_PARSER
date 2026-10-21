# pylint: disable=protected-access,too-many-statements
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.sources import SourceConfig
from app.storage import db
from app.storage.article_repo import ArticleRepo
from app.storage.models_sql import ArticleAlias, Base, Source
from app.storage.source_repo import SourceRepo


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


def test_list_for_view_applies_sort_without_query() -> None:
    session = _session()
    article_repo = ArticleRepo(session)
    now = datetime.now(UTC)

    article_repo.insert_article(
        source_id=None,
        title="Recent Low Rank",
        url="https://example.com/recent-no-query",
        url_canonical="https://example.com/recent-no-query",
        url_canonical_hash="nq1",
        published_at=now - timedelta(hours=1),
        rank_score=0.1,
    )
    article_repo.insert_article(
        source_id=None,
        title="Older High Rank",
        url="https://example.com/older-no-query",
        url_canonical="https://example.com/older-no-query",
        url_canonical_hash="nq2",
        published_at=now - timedelta(hours=2),
        rank_score=0.9,
    )

    by_published = article_repo.list_for_view(
        hours=24,
        limit=10,
        query=None,
        days=7,
        sort="published",
    )

    assert [row[0].title for row in by_published] == [
        "Recent Low Rank",
        "Older High Rank",
    ]


def test_list_for_view_applies_rank_sort_without_query() -> None:
    session = _session()
    article_repo = ArticleRepo(session)
    now = datetime.now(UTC)

    article_repo.insert_article(
        source_id=None,
        title="Recent Low Rank 2",
        url="https://example.com/recent-no-query-rank",
        url_canonical="https://example.com/recent-no-query-rank",
        url_canonical_hash="nq3",
        published_at=now - timedelta(hours=1),
        rank_score=0.1,
    )
    article_repo.insert_article(
        source_id=None,
        title="Older High Rank 2",
        url="https://example.com/older-no-query-rank",
        url_canonical="https://example.com/older-no-query-rank",
        url_canonical_hash="nq4",
        published_at=now - timedelta(hours=2),
        rank_score=0.9,
    )

    by_rank = article_repo.list_for_view(
        hours=24,
        limit=10,
        query=None,
        days=7,
        sort="rank",
    )

    assert [row[0].title for row in by_rank] == [
        "Older High Rank 2",
        "Recent Low Rank 2",
    ]


def test_source_repo_fallback_upsert_and_fetch_state_edge_cases() -> None:
    source_cfg = SourceConfig(
        id="source_fallback",
        name="Fallback Source",
        type="rss",
        url="https://example.com/feed",
        enabled=False,
        fetch_interval_minutes=45,
        source_weight=2.5,
    )

    class _ExecResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Session:
        def __init__(self) -> None:
            self.added: list[Source] = []
            self.flush_calls = 0
            self._existing: Source | None = None

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="mysql"))

        def execute(self, stmt):
            _ = stmt
            return _ExecResult(self._existing)

        def add(self, source: Source) -> None:
            self.added.append(source)

        def flush(self) -> None:
            self.flush_calls += 1

        def get(self, model, source_id: int):
            _ = (model, source_id)
            return self._existing

    session = _Session()
    repo = SourceRepo(session)

    created = repo.upsert_source(source_cfg)
    session._existing = created

    assert created.source_key == "source_fallback"
    assert created.name == "Fallback Source"
    assert created.enabled is False
    assert created.fetch_interval_minutes == 45
    assert created.source_weight == 2.5
    assert session.added == [created]
    assert session.flush_calls == 1

    created.name = "stale"
    updated = repo.upsert_source(
        SourceConfig(
            id="source_fallback",
            name="Fallback Source Updated",
            type="rss",
            url="https://example.com/updated",
            enabled=True,
            fetch_interval_minutes=15,
            source_weight=1.5,
        )
    )
    assert updated is created
    assert updated.name == "Fallback Source Updated"
    assert updated.type == "rss"
    assert updated.url == "https://example.com/updated"
    assert updated.enabled is True

    naive_time = datetime(2026, 2, 28, 12, 0, 0)
    created.last_checked_at = naive_time
    state = repo.get_fetch_state(source_id=1)
    assert state["last_checked_at"] == naive_time.replace(tzinfo=UTC)

    aware_time = datetime(2026, 2, 28, 13, 0, 0, tzinfo=UTC)
    repo.update_fetch_state(
        source_id=1,
        etag="etag-1",
        last_modified="Mon, 01 Jan 2024 00:00:00 GMT",
        last_checked_at=aware_time,
        last_status_code=304,
    )
    assert created.etag == "etag-1"
    assert created.last_modified == "Mon, 01 Jan 2024 00:00:00 GMT"
    assert created.last_checked_at == aware_time
    assert created.last_status_code == 304

    session._existing = None
    try:
        repo.get_fetch_state(source_id=99)
    except ValueError as exc:
        assert "source not found" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing source")

    try:
        repo.update_fetch_state(
            source_id=99,
            etag=None,
            last_modified=None,
            last_checked_at=aware_time,
            last_status_code=None,
        )
    except ValueError as exc:
        assert "source not found" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing source")


def test_article_repo_batch_fallback_and_empty_hashes() -> None:
    class _ExecResult:
        @staticmethod
        def scalars():
            return SimpleNamespace(all=lambda: [])

    class _Session:
        @staticmethod
        def get_bind():
            return SimpleNamespace(dialect=SimpleNamespace(name="mysql"))

        @staticmethod
        def execute(stmt):
            _ = stmt
            return _ExecResult()

    article_repo = ArticleRepo(_Session())
    insert_calls: list[dict[str, object]] = []
    insert_results = iter(
        [
            (SimpleNamespace(id=1), True),
            (SimpleNamespace(id=2), False),
        ]
    )

    def _fake_insert_article(**kwargs):
        insert_calls.append(kwargs)
        return next(insert_results)

    article_repo.insert_article = _fake_insert_article  # type: ignore[method-assign]

    assert article_repo.existing_canonical_hashes([]) == set()

    new_count, duplicate_count = article_repo.upsert_articles_batch(
        [
            {
                "source_id": None,
                "title": "A",
                "url": "https://example.com/a",
                "url_canonical": "https://example.com/a",
                "url_canonical_hash": "h-a",
                "published_at": datetime.now(UTC),
                "summary": None,
                "content": None,
                "ai_relevance_score": 0.1,
                "freshness_score": 0.1,
                "rank_score": 0.1,
            },
            {
                "source_id": None,
                "title": "B",
                "url": "https://example.com/b",
                "url_canonical": "https://example.com/b",
                "url_canonical_hash": "h-b",
                "published_at": datetime.now(UTC),
                "summary": None,
                "content": None,
                "ai_relevance_score": 0.2,
                "freshness_score": 0.2,
                "rank_score": 0.2,
            },
            {
                "source_id": None,
                "title": "B newer",
                "url": "https://example.com/b",
                "url_canonical": "https://example.com/b",
                "url_canonical_hash": "h-b",
                "published_at": datetime.now(UTC),
                "summary": None,
                "content": None,
                "ai_relevance_score": 0.9,
                "freshness_score": 0.9,
                "rank_score": 0.9,
            },
        ]
    )

    assert new_count == 1
    assert duplicate_count == 2
    assert len(insert_calls) == 2
    assert insert_calls[1]["ai_relevance_score"] == 0.9


def test_prune_older_than_and_count() -> None:
    session = _session()
    source_repo = SourceRepo(session)
    article_repo = ArticleRepo(session)
    now = datetime.now(UTC)
    source = source_repo.upsert_source(
        SourceConfig(
            id="prune_source",
            name="Prune Source",
            type="rss",
            url="https://example.com/prune-feed",
            enabled=True,
        )
    )

    recent, _ = article_repo.insert_article(
        source_id=None,
        title="Recent",
        url="https://example.com/recent-prune",
        url_canonical="https://example.com/recent-prune",
        url_canonical_hash="pr1",
        published_at=now - timedelta(days=5),
    )
    old, _ = article_repo.insert_article(
        source_id=None,
        title="Old",
        url="https://example.com/old-prune",
        url_canonical="https://example.com/old-prune",
        url_canonical_hash="pr2",
        published_at=now - timedelta(days=150),
    )
    session.add(ArticleAlias(
        article_id=old.id,
        source_id=source.id,
        url="https://example.com/old-prune/alias",
        discovered_at=now,
    ))
    session.commit()

    assert article_repo.count_older_than(older_than_days=100) == 1
    deleted_articles, deleted_aliases = article_repo.prune_older_than(older_than_days=100)
    session.commit()

    assert deleted_articles == 1
    assert deleted_aliases == 1
    assert article_repo.count_older_than(older_than_days=100) == 0

    remaining = article_repo.search(query="Recent", days=365, limit=10)
    assert [row.id for row in remaining] == [recent.id]


def test_list_for_view_date_range_skips_hours_and_days_windows() -> None:
    session = _session()
    article_repo = ArticleRepo(session)
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)

    article_repo.insert_article(
        source_id=None,
        title="Inside Day Window",
        url="https://example.com/date-range-inside",
        url_canonical="https://example.com/date-range-inside",
        url_canonical_hash="dr1",
        published_at=now,
        summary="match me",
        content="match me too",
        rank_score=0.4,
    )
    article_repo.insert_article(
        source_id=None,
        title="Previous Day",
        url="https://example.com/date-range-prev",
        url_canonical="https://example.com/date-range-prev",
        url_canonical_hash="dr2",
        published_at=now - timedelta(days=1, hours=1),
        summary="match me",
        content="match me too",
        rank_score=0.9,
    )
    article_repo.insert_article(
        source_id=None,
        title="Next Day",
        url="https://example.com/date-range-next",
        url_canonical="https://example.com/date-range-next",
        url_canonical_hash="dr3",
        published_at=now + timedelta(days=1, hours=1),
        summary="match me",
        content="match me too",
        rank_score=0.1,
    )

    target_day = now.date()

    no_query = article_repo.list_for_view(
        hours=1,
        limit=10,
        query=None,
        days=1,
        sort="published",
        date_from=target_day,
        date_to=target_day,
    )
    with_query = article_repo.list_for_view(
        hours=1,
        limit=10,
        query="match",
        days=1,
        sort="rank",
        date_from=target_day,
        date_to=target_day,
    )

    assert [row[0].title for row in no_query] == ["Inside Day Window"]
    assert [row[0].title for row in with_query] == ["Inside Day Window"]


def test_list_for_view_supports_open_ended_date_ranges() -> None:
    session = _session()
    article_repo = ArticleRepo(session)
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)

    older = now - timedelta(days=2)
    middle = now
    newer = now + timedelta(days=2)

    for title, url_suffix, published_at in [
        ("Older Open Range", "older-open", older),
        ("Middle Open Range", "middle-open", middle),
        ("Newer Open Range", "newer-open", newer),
    ]:
        article_repo.insert_article(
            source_id=None,
            title=title,
            url=f"https://example.com/{url_suffix}",
            url_canonical=f"https://example.com/{url_suffix}",
            url_canonical_hash=f"open-{url_suffix}",
            published_at=published_at,
            rank_score=0.5,
        )

    only_from = article_repo.list_for_view(
        hours=1,
        limit=10,
        query=None,
        days=1,
        sort="published",
        date_from=middle.date(),
        date_to=None,
    )
    only_to = article_repo.list_for_view(
        hours=1,
        limit=10,
        query=None,
        days=1,
        sort="published",
        date_from=None,
        date_to=middle.date(),
    )

    assert [row[0].title for row in only_from] == ["Newer Open Range", "Middle Open Range"]
    assert [row[0].title for row in only_to] == ["Middle Open Range", "Older Open Range"]


def test_source_repo_fetch_state_round_trip() -> None:
    session = _session()
    source_repo = SourceRepo(session)

    source = source_repo.upsert_source(
        SourceConfig(
            id="rss_stateful",
            name="RSS Stateful",
            type="rss",
            url="https://example.com/rss-stateful.xml",
            enabled=True,
        )
    )

    get_fetch_state = source_repo.get_fetch_state
    update_fetch_state = source_repo.update_fetch_state

    initial = get_fetch_state(source_id=source.id)
    assert initial == {
        "etag": None,
        "last_modified": None,
        "last_checked_at": None,
        "last_status_code": None,
    }

    checked_at = datetime(2026, 2, 23, 12, 34, 56, tzinfo=UTC)
    update_fetch_state(
        source_id=source.id,
        etag='"etag-v2"',
        last_modified="Mon, 23 Feb 2026 12:34:00 GMT",
        last_checked_at=checked_at,
        last_status_code=304,
    )
    session.commit()

    after = get_fetch_state(source_id=source.id)
    assert after == {
        "etag": '"etag-v2"',
        "last_modified": "Mon, 23 Feb 2026 12:34:00 GMT",
        "last_checked_at": checked_at,
        "last_status_code": 304,
    }

    persisted = session.get(Source, source.id)
    assert persisted is not None
    assert persisted.etag == '"etag-v2"'
    assert persisted.last_modified == "Mon, 23 Feb 2026 12:34:00 GMT"
    assert persisted.last_checked_at == checked_at
    assert persisted.last_status_code == 304


def test_article_repo_existing_canonical_hashes_returns_present_subset() -> None:
    session = _session()
    article_repo = ArticleRepo(session)
    now = datetime.now(UTC)

    article_repo.insert_article(
        source_id=None,
        title="One",
        url="https://example.com/one",
        url_canonical="https://example.com/one",
        url_canonical_hash="h-one",
        published_at=now,
    )
    article_repo.insert_article(
        source_id=None,
        title="Two",
        url="https://example.com/two",
        url_canonical="https://example.com/two",
        url_canonical_hash="h-two",
        published_at=now,
    )

    assert article_repo.existing_canonical_hashes(
        ["missing", "h-two", "h-one", "missing-2"]
    ) == {"h-one", "h-two"}
