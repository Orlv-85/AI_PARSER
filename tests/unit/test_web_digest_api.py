from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base
from app.web.app import create_app


def test_news_links_filters_to_requested_date_and_returns_article_metadata(
    monkeypatch, tmp_path
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
            )
            return [(article, "feed-key", "Feed Source")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

    client = TestClient(create_app())

    response = client.get("/api/news/links?date=2026-03-01&limit=25&min_ai_relevance=0.4")

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


def test_news_digests_rejects_blank_group_titles_and_item_summaries(
    monkeypatch, tmp_path
) -> None:
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
