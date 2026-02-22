# pylint: disable=import-outside-toplevel,useless-return

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

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


@pytest.fixture(autouse=True)
def _disable_mcp_auth_by_default(monkeypatch) -> None:
    from app.mcp import server as mcp_server_module

    monkeypatch.setattr(
        mcp_server_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=False, mcp_auth_token=None),
        raising=False,
    )


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


def test_news_list_denies_unauthenticated_call_when_mcp_auth_enabled(monkeypatch, caplog) -> None:
    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_agent(self, **_kwargs):
            row = type(
                "_Article",
                (),
                {
                    "id": 88,
                    "title": "Auth News",
                    "published_at": datetime(2026, 2, 21, 6, 0, tzinfo=UTC),
                    "rank_score": 0.7,
                    "url_canonical": "https://example.com/auth-news",
                    "source_id": 1,
                    "content": "content",
                },
            )()
            return [(row, "auth-src", "Auth Source")]

    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    from app.mcp import server as mcp_server_module

    monkeypatch.setattr(
        mcp_server_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=True, mcp_auth_token="top-secret-token"),
        raising=False,
    )

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

    assert payload["ok"] is False
    assert payload["error_type"] == "auth_error"
    assert "mcp_auth_failed" in caplog.text
    assert "top-secret-token" not in caplog.text


def test_news_list_allows_valid_token_and_logs_auth_without_secret_leakage(
    monkeypatch, caplog
) -> None:
    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_agent(self, **_kwargs):
            row = type(
                "_Article",
                (),
                {
                    "id": 89,
                    "title": "Allowed News",
                    "published_at": datetime(2026, 2, 21, 6, 30, tzinfo=UTC),
                    "rank_score": 0.9,
                    "url_canonical": "https://example.com/allowed-news",
                    "source_id": 1,
                    "content": "content",
                },
            )()
            return [(row, "auth-src", "Auth Source")]

    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    from app.mcp import server as mcp_server_module

    monkeypatch.setattr(
        mcp_server_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=True, mcp_auth_token="top-secret-token"),
        raising=False,
    )

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
        denied = service.news_list(limit=1, auth_token="wrong-token")
        allowed = service.news_list(limit=1, auth_token="top-secret-token")
    finally:
        mcp_server_module.ArticleRepo = original_repo

    assert denied["ok"] is False
    assert denied["error_type"] == "auth_error"
    assert allowed["ok"] is True
    assert allowed["count"] == 1
    assert "mcp_auth_failed" in caplog.text
    assert "mcp_auth_success" in caplog.text
    assert "top-secret-token" not in caplog.text
    assert "wrong-token" not in caplog.text


def test_news_list_keeps_backward_compatibility_when_mcp_auth_disabled(monkeypatch) -> None:
    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_agent(self, **_kwargs):
            row = type(
                "_Article",
                (),
                {
                    "id": 90,
                    "title": "No Auth Required",
                    "published_at": datetime(2026, 2, 21, 7, 30, tzinfo=UTC),
                    "rank_score": 0.8,
                    "url_canonical": "https://example.com/no-auth",
                    "source_id": 1,
                    "content": "content",
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

    monkeypatch.setattr(
        mcp_server_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=False, mcp_auth_token=None),
        raising=False,
    )

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
        ).news_list(limit=1)
    finally:
        mcp_server_module.ArticleRepo = original_repo

    assert payload["ok"] is True
    assert payload["count"] == 1


def test_news_get_denies_unauthenticated_call_when_mcp_auth_enabled(monkeypatch, caplog) -> None:
    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def get_article_for_agent(self, *, article_id: int):
            _ = article_id
            raise AssertionError("repo should not be called when auth is denied")

    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    from app.mcp import server as mcp_server_module

    monkeypatch.setattr(
        mcp_server_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=True, mcp_auth_token="top-secret-token"),
        raising=False,
    )

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
        payload = service.news_get(article_id=1)
    finally:
        mcp_server_module.ArticleRepo = original_repo

    assert payload["ok"] is False
    assert payload["error_type"] == "auth_error"
    assert "mcp_auth_failed" in caplog.text
    assert "top-secret-token" not in caplog.text


def test_news_update_status_applies_mcp_auth_enforcement(monkeypatch, caplog) -> None:
    from app.mcp import server as mcp_server_module

    monkeypatch.setattr(
        mcp_server_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=True, mcp_auth_token="top-secret-token"),
        raising=False,
    )

    service = MCPNewsService(
        update_service=_UpdateService(
            started=UpdateStatus(status="idle"),
            current=UpdateStatus(status="idle"),
        ),
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )
    caplog.set_level(logging.INFO, logger="app.mcp.server")
    denied = service.news_update_status()
    allowed = service.news_update_status(auth_token="top-secret-token")

    assert denied["ok"] is False
    assert denied["error_type"] == "auth_error"
    assert allowed["ok"] is True
    assert allowed["status"]["status"] == "idle"
    assert "mcp_auth_failed" in caplog.text
    assert "mcp_auth_success" in caplog.text
    assert "top-secret-token" not in caplog.text


def test_news_update_applies_mcp_auth_enforcement(monkeypatch, caplog) -> None:
    from app.mcp import server as mcp_server_module

    monkeypatch.setattr(
        mcp_server_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=True, mcp_auth_token="top-secret-token"),
        raising=False,
    )

    status = UpdateStatus(
        run_id="20260222000100",
        status="running",
        started_at=datetime(2026, 2, 22, 0, 1, 0, tzinfo=UTC),
        fetched=0,
        new=0,
        duplicates=0,
        errors=0,
    )
    service = MCPNewsService(
        update_service=_UpdateService(started=status, current=status),
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )
    caplog.set_level(logging.INFO, logger="app.mcp.server")

    denied_missing = service.news_update()
    denied_wrong = service.news_update(auth_token="wrong-token")
    allowed = service.news_update(auth_token="top-secret-token")

    assert denied_missing["ok"] is False
    assert denied_missing["error_type"] == "auth_error"
    assert denied_wrong["ok"] is False
    assert denied_wrong["error_type"] == "auth_error"
    assert allowed["ok"] is True
    assert allowed["status"]["run_id"] == "20260222000100"
    assert "mcp_auth_failed" in caplog.text
    assert "mcp_auth_success" in caplog.text
    assert "top-secret-token" not in caplog.text
    assert "wrong-token" not in caplog.text


def test_build_mcp_server_rejects_missing_mcp_token_when_auth_enabled(monkeypatch) -> None:
    from app.mcp import server as mcp_server_module

    class _FakeMCP:
        def __init__(self, _name: str) -> None:
            pass

        def tool(self, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

        def run(self) -> None:
            return None

    monkeypatch.setattr(mcp_server_module, "FastMCP", _FakeMCP, raising=False)
    monkeypatch.setattr(
        mcp_server_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=True, mcp_auth_token="   "),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="AINEWS_MCP_AUTH_TOKEN is missing"):
        mcp_server_module.build_mcp_server()


def test_news_update_wait_returns_terminal_status() -> None:
    class _PollingUpdateService:
        def __init__(self) -> None:
            self._started = UpdateStatus(
                run_id="run-1",
                status="running",
                started_at=datetime(2026, 2, 22, 0, 1, 0, tzinfo=UTC),
                fetched=0,
                new=0,
                duplicates=0,
                errors=0,
            )
            self._current_calls = 0

        def start(self, runtime_settings):
            _ = runtime_settings
            return self._started

        def current_status(self) -> UpdateStatus:
            self._current_calls += 1
            if self._current_calls >= 2:
                return UpdateStatus(
                    run_id="run-1",
                    status="finished",
                    started_at=datetime(2026, 2, 22, 0, 1, 0, tzinfo=UTC),
                    finished_at=datetime(2026, 2, 22, 0, 1, 2, tzinfo=UTC),
                    fetched=2,
                    new=1,
                    duplicates=1,
                    errors=0,
                )
            return self._started

    service = MCPNewsService(
        update_service=_PollingUpdateService(),
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )

    payload = service.news_update(wait=True, poll_interval_seconds=0.1, max_wait_seconds=1.0)

    assert payload["ok"] is True
    assert payload["status"]["status"] == "finished"


def test_news_update_wait_timeout_returns_timeout_error() -> None:
    running = UpdateStatus(
        run_id="run-timeout",
        status="running",
        started_at=datetime(2026, 2, 22, 0, 2, 0, tzinfo=UTC),
        fetched=0,
        new=0,
        duplicates=0,
        errors=0,
    )
    service = MCPNewsService(
        update_service=_UpdateService(started=running, current=running),
        session_factory=lambda: None,
        create_all_fn=lambda: None,
    )

    payload = service.news_update(wait=True, poll_interval_seconds=0.1, max_wait_seconds=1.0)

    assert payload["ok"] is False
    assert payload["error_type"] == "timeout"
    assert payload["status"]["run_id"] == "run-timeout"


def test_build_mcp_server_requires_fastmcp_dependency(monkeypatch) -> None:
    from app.mcp import server as mcp_server_module

    monkeypatch.setattr(mcp_server_module, "FastMCP", None, raising=False)

    with pytest.raises(RuntimeError, match="fastmcp is not installed"):
        mcp_server_module.build_mcp_server()


def test_build_mcp_server_registers_and_delegates_tools(monkeypatch) -> None:
    from app.mcp import server as mcp_server_module

    calls: dict[str, dict[str, object]] = {}

    class _FakeService:
        def news_update(self, **kwargs):
            calls["news.update"] = kwargs
            return {"ok": True, "tool": "update"}

        def news_update_status(self, **kwargs):
            calls["news.update_status"] = kwargs
            return {"ok": True, "tool": "status"}

        def news_list(self, **kwargs):
            calls["news.list"] = kwargs
            return {"ok": True, "tool": "list"}

        def news_get(self, **kwargs):
            calls["news.get"] = kwargs
            return {"ok": True, "tool": "get"}

    class _FakeMCP:
        def __init__(self, _name: str) -> None:
            self.tools: dict[str, object] = {}

        def tool(self, *, name: str):
            def _decorator(func):
                self.tools[name] = func
                return func

            return _decorator

        def run(self) -> None:
            return None

    monkeypatch.setattr(
        mcp_server_module,
        "get_settings",
        lambda: SimpleNamespace(mcp_auth_enabled=False, mcp_auth_token=None),
        raising=False,
    )
    monkeypatch.setattr(mcp_server_module, "MCPNewsService", _FakeService, raising=False)
    monkeypatch.setattr(mcp_server_module, "FastMCP", _FakeMCP, raising=False)

    mcp = cast(Any, mcp_server_module.build_mcp_server())
    tools = mcp.__dict__["tools"]
    assert set(tools.keys()) == {"news.update", "news.update_status", "news.list", "news.get"}

    update_payload = tools["news.update"](
        wait=True,
        poll_interval_seconds=0.5,
        max_wait_seconds=3.0,
        request_timeout_seconds=10.0,
        max_retries=2,
        per_source_min_interval_seconds=0.1,
        concurrency_limit=2,
        auth_token="tok",
    )
    status_payload = tools["news.update_status"](auth_token="tok")
    list_payload = tools["news.list"](
        hours=2,
        limit=3,
        min_ai_relevance=0.4,
        query="q",
        days=5,
        sort="published",
        auth_token="tok",
    )
    get_payload = tools["news.get"](article_id=7, auth_token="tok")

    assert update_payload["tool"] == "update"
    assert status_payload["tool"] == "status"
    assert list_payload["tool"] == "list"
    assert get_payload["tool"] == "get"
    assert calls["news.update"]["wait"] is True
    assert calls["news.update_status"]["auth_token"] == "tok"
    assert calls["news.list"]["sort"] == "published"
    assert calls["news.get"]["article_id"] == 7


def test_run_mcp_server_calls_mcp_run(monkeypatch) -> None:
    from app.mcp import server as mcp_server_module

    called = {"run": 0}

    class _Runner:
        def run(self) -> None:
            called["run"] += 1

    def _build_mcp_server():
        return _Runner()

    monkeypatch.setattr(mcp_server_module, "build_mcp_server", _build_mcp_server, raising=False)

    mcp_server_module.run_mcp_server()
    assert called["run"] == 1
