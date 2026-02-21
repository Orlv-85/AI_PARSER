# pylint: disable=import-outside-toplevel,useless-return

import logging
from datetime import UTC, datetime

from app.mcp.server import MCPNewsService
from app.web.models import UpdateStatus


class _UpdateService:
    def __init__(self, *, started: UpdateStatus | None, current: UpdateStatus) -> None:
        self._started = started
        self._current = current
        self.runtime_settings = None

    def start(self, runtime_settings):
        self.runtime_settings = runtime_settings
        return self._started

    def current_status(self) -> UpdateStatus:
        return self._current


def test_news_update_validation_error() -> None:
    status = UpdateStatus(status="idle")
    update_service = _UpdateService(started=status, current=status)
    service = MCPNewsService(
        update_service=update_service,
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )

    payload = service.news_update(poll_interval_seconds=0.01)

    assert payload["ok"] is False
    assert payload["error_type"] == "validation_error"


def test_news_update_already_running_conflict() -> None:
    running = UpdateStatus(
        run_id="20260221123456",
        status="running",
        started_at=datetime(2026, 2, 21, 12, 34, 56, tzinfo=UTC),
        fetched=1,
        new=1,
        duplicates=0,
        errors=0,
    )
    update_service = _UpdateService(started=None, current=running)
    service = MCPNewsService(
        update_service=update_service,
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )

    payload = service.news_update()

    assert payload == {
        "ok": False,
        "error_type": "already_running",
        "status": {
            "run_id": "20260221123456",
            "status": "running",
            "started_at": "2026-02-21T12:34:56+00:00",
            "finished_at": None,
            "fetched": 1,
            "new": 1,
            "duplicates": 0,
            "errors": 0,
            "error_message": None,
        },
    }


def test_news_update_status_returns_serialized_status() -> None:
    finished = UpdateStatus(
        run_id="20260221130000",
        status="finished",
        started_at=datetime(2026, 2, 21, 12, 59, 0, tzinfo=UTC),
        finished_at=datetime(2026, 2, 21, 13, 0, 0, tzinfo=UTC),
        fetched=4,
        new=3,
        duplicates=1,
        errors=0,
    )
    service = MCPNewsService(
        update_service=_UpdateService(started=finished, current=finished),
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )

    payload = service.news_update_status()

    assert payload["ok"] is True
    assert payload["status"]["status"] == "finished"
    assert payload["status"]["run_id"] == "20260221130000"


def test_news_list_validation_error() -> None:
    status = UpdateStatus(status="idle")
    service = MCPNewsService(
        update_service=_UpdateService(started=status, current=status),
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )

    payload = service.news_list(limit=0)

    assert payload["ok"] is False
    assert payload["error_type"] == "validation_error"


def test_news_list_success() -> None:
    captured: dict[str, object] = {}
    create_calls = {"count": 0}

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_agent(self, **kwargs):
            captured.update(kwargs)
            row = type(
                "_Article",
                (),
                {
                    "id": 11,
                    "title": "AI News",
                    "published_at": datetime(2026, 2, 21, 9, 0, tzinfo=UTC),
                    "rank_score": 0.95,
                    "url_canonical": "https://example.com/ai-news",
                    "source_id": 5,
                    "content": "full text",
                },
            )()
            return [(row, "rss-key", "RSS Source")]

    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def _create_all() -> None:
        create_calls["count"] += 1

    service = MCPNewsService(
        update_service=_UpdateService(
            started=UpdateStatus(status="idle"),
            current=UpdateStatus(status="idle"),
        ),
        session_factory=_SessionFactory(),
        create_all_fn=_create_all,
    )

    from app.mcp import server as mcp_server_module

    original_repo = mcp_server_module.ArticleRepo
    mcp_server_module.ArticleRepo = _ArticleRepo
    try:
        payload = service.news_list(
            hours=12,
            limit=15,
            min_ai_relevance=0.4,
            query="agent",
            days=3,
            sort="published",
        )
    finally:
        mcp_server_module.ArticleRepo = original_repo

    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["items"][0]["article_id"] == 11
    assert payload["items"][0]["source_key"] == "rss-key"
    assert payload["items"][0]["has_content"] is True
    assert create_calls["count"] == 1
    assert captured == {
        "hours": 12,
        "limit": 15,
        "min_ai_relevance": 0.4,
        "query": "agent",
        "days": 3,
        "sort": "published",
    }


def test_news_get_validation_error_and_not_found() -> None:
    service = MCPNewsService(
        update_service=_UpdateService(
            started=UpdateStatus(status="idle"),
            current=UpdateStatus(status="idle"),
        ),
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )

    invalid = service.news_get(article_id=0)

    assert invalid == {
        "ok": False,
        "error_type": "validation_error",
        "detail": "article_id must be positive",
    }

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def get_article_for_agent(self, *, article_id: int):
            _ = article_id
            return None

    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    from app.mcp import server as mcp_server_module

    original_repo = mcp_server_module.ArticleRepo
    mcp_server_module.ArticleRepo = _ArticleRepo
    try:
        not_found = MCPNewsService(
            update_service=_UpdateService(
                started=UpdateStatus(status="idle"),
                current=UpdateStatus(status="idle"),
            ),
            session_factory=_SessionFactory(),
            create_all_fn=lambda: None,
        ).news_get(article_id=999)
    finally:
        mcp_server_module.ArticleRepo = original_repo

    assert not_found == {
        "ok": False,
        "error_type": "not_found",
        "detail": "article not found",
    }


def test_news_get_success() -> None:
    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def get_article_for_agent(self, *, article_id: int):
            _ = article_id
            row = type(
                "_Article",
                (),
                {
                    "id": 42,
                    "title": "Detailed News",
                    "summary": "short summary",
                    "content": "long full content",
                    "published_at": datetime(2026, 2, 20, 8, 30, tzinfo=UTC),
                    "rank_score": 0.81,
                    "url": "https://example.com/detail",
                    "url_canonical": "https://example.com/detail",
                    "source_id": 2,
                },
            )()
            return (row, "src-2", "Source 2")

    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    from app.mcp import server as mcp_server_module

    original_repo = mcp_server_module.ArticleRepo
    mcp_server_module.ArticleRepo = _ArticleRepo
    try:
        payload = MCPNewsService(
            update_service=_UpdateService(
                started=UpdateStatus(status="idle"),
                current=UpdateStatus(status="idle"),
            ),
            session_factory=_SessionFactory(),
            create_all_fn=lambda: None,
        ).news_get(article_id=42)
    finally:
        mcp_server_module.ArticleRepo = original_repo

    assert payload["ok"] is True
    assert payload["item"]["article_id"] == 42
    assert payload["item"]["source_key"] == "src-2"
    assert payload["item"]["source_name"] == "Source 2"


def test_news_update_logs_validation_and_conflict_outcomes(caplog) -> None:
    service = MCPNewsService(
        update_service=_UpdateService(
            started=None,
            current=UpdateStatus(status="running"),
        ),
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )

    caplog.set_level(logging.INFO, logger="app.mcp.server")
    invalid = service.news_update(poll_interval_seconds=0.01)
    conflict = service.news_update()

    assert invalid["ok"] is False
    assert invalid["error_type"] == "validation_error"
    assert conflict["ok"] is False
    assert conflict["error_type"] == "already_running"
    assert "news.update" in caplog.text
    assert "validation_error" in caplog.text
    assert "already_running" in caplog.text


def test_news_list_logs_data_access_outcome(caplog) -> None:
    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_agent(self, **_kwargs):
            row = type(
                "_Article",
                (),
                {
                    "id": 77,
                    "title": "Logged News",
                    "published_at": datetime(2026, 2, 21, 7, 0, tzinfo=UTC),
                    "rank_score": 0.6,
                    "url_canonical": "https://example.com/logged",
                    "source_id": 1,
                    "content": None,
                },
            )()
            return [(row, "src", "Source")]

    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    from app.mcp import server as mcp_server_module

    original_repo = mcp_server_module.ArticleRepo
    mcp_server_module.ArticleRepo = _ArticleRepo
    try:
        service = MCPNewsService(
            update_service=_UpdateService(
                started=UpdateStatus(status="idle"),
                current=UpdateStatus(status="idle"),
            ),
            session_factory=_SessionFactory(),
            create_all_fn=lambda: None,
        )
        caplog.set_level(logging.INFO, logger="app.mcp.server")
        payload = service.news_list(limit=1)
    finally:
        mcp_server_module.ArticleRepo = original_repo

    assert payload["ok"] is True
    assert payload["count"] == 1
    assert "news.list" in caplog.text
    assert "count=1" in caplog.text
