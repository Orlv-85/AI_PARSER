from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Article, Base, FetchRun, Source
from app.web.app import create_app
from app.web.routes import news as news_routes
from app.web.routes import pages as pages_routes


@pytest.mark.parametrize("include_content", [False, True])
def test_news_links_filters_to_requested_date_and_returns_article_metadata(
    monkeypatch, tmp_path, include_content
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def _session_local():
        return _DummySession()

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_agent(self, **kwargs):
            captured.update(kwargs)
            article = SimpleNamespace(
                id=42,
                title="Daily Link Feed",
                published_at=datetime(2026, 3, 1, 9, 30, tzinfo=UTC),
                url="https://example.com/source-article",
                url_canonical="https://example.com/source-article",
                source_id=9,
                summary="Article summary",
                content="x" * 13000,
            )
            return [(article, "feed-key", "Feed Source")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(news_routes, "ArticleRepo", _ArticleRepo)

    client = TestClient(create_app())

    query = "/api/news/links?date=2026-03-01&limit=25&min_ai_relevance=0.4"
    response = client.get(query + ("&include_content=true" if include_content else ""))

    assert response.status_code == 200
    assert captured == {
        "hours": None,
        "limit": 25,
        "offset": 0,
        "query": None,
        "days": 1,
        "sort": "published",
        "min_ai_relevance": 0.4,
        "date_from": datetime(2026, 3, 1, tzinfo=UTC).date(),
        "date_to": datetime(2026, 3, 1, tzinfo=UTC).date(),
    }
    assert response.json() == [
        {
            "article_id": 42,
            "title": "Daily Link Feed",
            "published_at": "2026-03-01T09:30:00Z",
            "url": "https://example.com/source-article",
            "url_canonical": "https://example.com/source-article",
            "source_id": 9,
            "source_key": "feed-key",
            "source_name": "Feed Source",
            **({"summary": "Article summary", "content": "x" * 12000} if include_content else {}),
        }
    ]


def test_news_links_returns_503_when_storage_is_unavailable(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    web_app_module = import_module("app.web.app")

    def _raise_db_error() -> None:
        raise SQLAlchemyError()

    monkeypatch.setattr(web_app_module, "create_all", _raise_db_error)

    client = TestClient(create_app())

    response = client.get("/api/news/links?date=2026-03-01")

    assert response.status_code == 503


def test_news_digests_post_and_get_round_trip(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/web-digest-roundtrip.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)

    client = TestClient(create_app())

    publish = client.post(
        "/api/news/digests",
        json={
            "report_date": "2026-03-01",
            "groups": [
                {
                    "title": "Agents",
                    "items": [
                        {
                            "title": "Agent Tooling Consolidates",
                            "summary": "Vendors are packaging orchestration and evals together.",
                            "url": "https://example.com/agent-tooling",
                        }
                    ],
                }
            ],
        },
    )

    assert publish.status_code == 200
    assert publish.json() == {
        "report_date": "2026-03-01",
        "groups": [
            {
                "title": "Agents",
                "items": [
                    {
                        "title": "Agent Tooling Consolidates",
                        "summary": "Vendors are packaging orchestration and evals together.",
                        "url": "https://example.com/agent-tooling",
                    }
                ],
            }
        ],
    }

    fetch = client.get("/api/news/digests?date=2026-03-01")

    assert fetch.status_code == 200
    assert fetch.json() == publish.json()


def test_news_digests_get_returns_empty_state_for_missing_date(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/web-digest-empty.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)

    client = TestClient(create_app())

    response = client.get("/api/news/digests?date=2026-03-02")

    assert response.status_code == 200
    assert response.json() == {"report_date": "2026-03-02", "groups": []}


def test_news_daily_stats_api_returns_zero_days_and_fetch_counts(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/web-news-stats.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with session_local() as session:
        Base.metadata.create_all(bind=engine)
        source = Source(
            source_key="stats-source",
            name="Stats Source",
            type="rss",
            url="https://example.com/feed",
        )
        session.add(source)
        session.flush()
        session.add(
            Article(
                source_id=source.id,
                title="May 2 story",
                summary="Published after a zero day.",
                content=None,
                url="https://example.com/may-2",
                url_canonical="https://example.com/may-2",
                url_canonical_hash="may-2",
                published_at=datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
                discovered_at=datetime(2026, 5, 2, 9, 2, tzinfo=UTC),
                ai_relevance_score=0.9,
                freshness_score=0.8,
                rank_score=0.95,
            )
        )
        session.add_all(
            [
                FetchRun(
                    run_id="20260501010000",
                    started_at=datetime(2026, 5, 1, 1, 0, tzinfo=UTC),
                    finished_at=datetime(2026, 5, 1, 1, 2, tzinfo=UTC),
                    status="finished",
                    fetched_count=0,
                    new_count=0,
                    duplicate_count=0,
                    error_count=2,
                ),
                FetchRun(
                    run_id="20260502010000",
                    started_at=datetime(2026, 5, 2, 1, 0, tzinfo=UTC),
                    finished_at=datetime(2026, 5, 2, 1, 4, tzinfo=UTC),
                    status="finished",
                    fetched_count=10,
                    new_count=1,
                    duplicate_count=9,
                    error_count=0,
                ),
            ]
        )
        session.commit()

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)

    client = TestClient(create_app())

    response = client.get("/api/news/stats/daily?date_from=2026-05-01&date_to=2026-05-02")

    assert response.status_code == 200
    assert response.json() == {
        "date_from": "2026-05-01",
        "date_to": "2026-05-02",
        "items": [
            {
                "stat_date": "2026-05-01",
                "published_count": 0,
                "discovered_count": 0,
                "fetch_run_count": 1,
                "fetched_count": 0,
                "new_count": 0,
                "duplicate_count": 0,
                "error_count": 2,
            },
            {
                "stat_date": "2026-05-02",
                "published_count": 1,
                "discovered_count": 1,
                "fetch_run_count": 1,
                "fetched_count": 10,
                "new_count": 1,
                "duplicate_count": 9,
                "error_count": 0,
            },
        ],
    }


def test_news_stats_page_renders_public_shell(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 2, 9, 0, tzinfo=tz or UTC)

    monkeypatch.setattr(pages_routes, "datetime", _FrozenDateTime)

    client = TestClient(create_app())

    response = client.get("/news-stats")

    assert response.status_code == 200
    assert "News Stats" in response.text
    assert 'value="2026-03-03"' in response.text
    assert 'value="2026-05-01"' in response.text
    assert "/api/news/stats/daily?" in response.text


def test_news_digests_rejects_blank_group_titles_and_item_summaries(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/web-digest-invalid-text.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)

    client = TestClient(create_app())

    blank_group = client.post(
        "/api/news/digests",
        json={
            "report_date": "2026-03-01",
            "groups": [
                {
                    "title": "   ",
                    "items": [
                        {
                            "title": "Valid title",
                            "summary": "Valid summary",
                            "url": "https://example.com/valid",
                        }
                    ],
                }
            ],
        },
    )
    blank_summary = client.post(
        "/api/news/digests",
        json={
            "report_date": "2026-03-01",
            "groups": [
                {
                    "title": "Agents",
                    "items": [
                        {
                            "title": "Valid title",
                            "summary": "   ",
                            "url": "https://example.com/valid",
                        }
                    ],
                }
            ],
        },
    )

    assert blank_group.status_code == 422
    assert blank_summary.status_code == 422


def test_news_digests_rejects_invalid_item_urls(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path}/web-digest-invalid-url.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)

    client = TestClient(create_app())

    response = client.post(
        "/api/news/digests",
        json={
            "report_date": "2026-03-01",
            "groups": [
                {
                    "title": "Agents",
                    "items": [
                        {
                            "title": "Invalid link",
                            "summary": "This item should fail validation.",
                            "url": "not-a-url",
                        }
                    ],
                }
            ],
        },
    )

    assert response.status_code == 422
