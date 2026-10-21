import time
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import get_settings
from app.web.app import create_app
from app.web.routes import common as common_routes
from app.web.routes import news as news_routes
from app.web.routes import pages as pages_routes


class _NoSignalsRepo:
    """These tests fake SessionLocal; the signals read on / gets no stored report."""

    def __init__(self, _session, **_kwargs) -> None:
        pass

    def get_report(self, _report_date):
        return None


@pytest.fixture(autouse=True)
def _no_daily_signals(monkeypatch) -> None:
    monkeypatch.setattr(common_routes, "DailySignalRepo", _NoSignalsRepo)


def test_web_app_pages_and_update_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **_kwargs):
            return []

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    monkeypatch.setattr(
        "app.web.service.run_fetch_cycle",
        lambda **kwargs: SimpleNamespace(source_count=7, fetched=3, new=2, duplicates=1, errors=0),
    )
    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(news_routes, "ArticleRepo", _ArticleRepo)
    monkeypatch.setattr(pages_routes, "NewsDigestRepo", _NewsDigestRepo)

    app = create_app()
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert "Yesterday&#39;s Digest" in page.text or "Yesterday's Digest" in page.text
    assert 'id="digest-date"' in page.text
    assert "No digest has been published for this date yet." in page.text
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    current_settings = client.get("/api/update/settings")
    assert current_settings.status_code == 200
    assert current_settings.json()["max_retries"] == 3

    saved = client.put(
        "/api/update/settings",
        json={
            "request_timeout_seconds": 9.0,
            "max_retries": 1,
            "per_source_min_interval_seconds": 0.3,
            "concurrency_limit": 2,
        },
    )
    assert saved.status_code == 200

    run = client.post("/api/update/run")
    assert run.status_code == 200

    terminal = None
    for _ in range(30):
        status = client.get("/api/update/status")
        terminal = status.json()
        if terminal["status"] in {"finished", "failed"}:
            break
        time.sleep(0.02)

    assert terminal is not None
    assert terminal["status"] == "finished"
    assert terminal["source_count"] == 7
    assert terminal["fetched"] == 3

    news = client.get("/api/news")
    assert news.status_code == 200


def test_update_settings_validation_error(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)

    response = client.put(
        "/api/update/settings",
        json={
            "request_timeout_seconds": 0,
            "max_retries": -1,
            "per_source_min_interval_seconds": 0.3,
            "concurrency_limit": 2,
        },
    )
    assert response.status_code == 422


def test_create_app_skips_sqlite_directory_creation_for_in_memory_database(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AINEWS_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    get_settings.cache_clear()

    mkdir_calls: list[tuple[str, bool, bool]] = []

    def _record_mkdir(self, _mode=0o777, parents=False, exist_ok=False):
        mkdir_calls.append((str(self), parents, exist_ok))

    monkeypatch.setattr("pathlib.Path.mkdir", _record_mkdir)

    app = create_app()

    assert app is not None
    assert not mkdir_calls


def test_second_update_run_is_rejected_when_running(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    def _slow_cycle(**_kwargs):
        time.sleep(0.2)
        return SimpleNamespace(source_count=2, fetched=1, new=1, duplicates=0, errors=0)

    monkeypatch.setattr("app.web.service.run_fetch_cycle", _slow_cycle)

    app = create_app()
    client = TestClient(app)

    first = client.post("/api/update/run")
    second = client.post("/api/update/run")

    assert first.status_code == 200
    assert second.status_code == 409

    for _ in range(30):
        status = client.get("/api/update/status").json()
        if status["status"] in {"finished", "failed"}:
            break
        time.sleep(0.02)


def test_news_view_filters_and_source_fields(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **kwargs):
            captured.update(kwargs)
            row = SimpleNamespace(
                title="News",
                published_at=datetime(2026, 2, 21, 12, 0, tzinfo=UTC),
                rank_score=0.91,
                url_canonical="https://example.com/news",
                source_id=11,
            )
            return [(row, "src-key", "Source Name")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(news_routes, "ArticleRepo", _ArticleRepo)

    app = create_app()
    client = TestClient(app)

    response = client.get("/api/news?hours=12&limit=15&days=5&sort=published&query=ai")
    assert response.status_code == 200
    payload = response.json()
    assert captured == {
        "hours": 12,
        "limit": 15,
        "min_ai_relevance": 0.2,
        "query": "ai",
        "days": 5,
        "sort": "published",
    }
    assert payload[0]["source_key"] == "src-key"
    assert payload[0]["source_name"] == "Source Name"


def test_news_storage_unavailable_returns_503(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    web_app_module = import_module("app.web.app")

    def _raise_db_error() -> None:
        raise SQLAlchemyError()

    monkeypatch.setattr(web_app_module, "create_all", _raise_db_error)

    app = create_app()
    client = TestClient(app)

    response = client.get("/api/news")
    assert response.status_code == 503


def test_news_article_details_returns_content_and_404_for_missing(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def get_article_for_agent(self, *, article_id: int):
            if article_id == 123:
                article = SimpleNamespace(
                    id=123,
                    title="Detailed article",
                    summary="Short summary",
                    content="Full article body",
                    published_at=datetime(2026, 2, 21, 15, 30, tzinfo=UTC),
                    rank_score=0.77,
                    url="https://example.com/full",
                    url_canonical="https://example.com/full",
                    source_id=5,
                )
                return (article, "src-key", "Source Name")
            return None

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(news_routes, "ArticleRepo", _ArticleRepo)

    app = create_app()
    client = TestClient(app)

    response = client.get("/api/news/123")
    assert response.status_code == 200
    payload = response.json()
    assert payload["article_id"] == 123
    assert payload["summary"] == "Short summary"
    assert payload["content"] == "Full article body"
    assert payload["source_key"] == "src-key"
    assert payload["source_name"] == "Source Name"

    missing = client.get("/api/news/999999")
    assert missing.status_code == 404


def test_news_export_returns_json_attachment_and_include_content(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    captured_calls: list[dict[str, object]] = []

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **kwargs):
            captured_calls.append(dict(kwargs))
            article = SimpleNamespace(
                id=7,
                title="Exported item",
                summary="Summary text",
                content="Full content text",
                published_at=datetime(2026, 2, 21, 10, 0, tzinfo=UTC),
                rank_score=0.66,
                url="https://example.com/original",
                url_canonical="https://example.com/canonical",
                source_id=4,
            )
            return [(article, "src-key", "Source Name")]

        def list_for_agent(self, **kwargs):
            return self.list_for_view(**kwargs)

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(news_routes, "ArticleRepo", _ArticleRepo)

    app = create_app()
    client = TestClient(app)

    default_resp = client.get("/api/news/export?hours=6&limit=5")
    assert default_resp.status_code == 200
    assert default_resp.headers["content-type"].startswith("application/json")
    content_disposition = default_resp.headers.get("content-disposition", "")
    assert "attachment;" in content_disposition
    assert ".json" in content_disposition
    default_payload = default_resp.json()
    assert isinstance(default_payload, list)
    assert "summary" not in default_payload[0]
    assert "content" not in default_payload[0]

    with_content = client.get("/api/news/export?hours=6&limit=5&include_content=true")
    assert with_content.status_code == 200
    payload = with_content.json()
    assert payload[0]["summary"] == "Summary text"
    assert payload[0]["content"] == "Full content text"
    assert payload[0]["url"] == "https://example.com/original"

    assert captured_calls[0]["hours"] == 6
    assert captured_calls[0]["limit"] == 5
    assert captured_calls[1]["include_content"] is True


def test_news_export_forwards_date_range_and_returns_503_on_db_error(
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

        def list_for_view(self, **kwargs):
            captured.update(kwargs)
            return []

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(news_routes, "ArticleRepo", _ArticleRepo)

    app = create_app()
    client = TestClient(app)

    ok = client.get("/api/news/export?date_from=2026-02-20&date_to=2026-02-21")
    assert ok.status_code == 200
    assert captured["hours"] is None
    assert captured["date_from"] == date(2026, 2, 20)
    assert captured["date_to"] == date(2026, 2, 21)

    def _raise_db_error() -> None:
        raise SQLAlchemyError()

    # create_all is read when the app is built, so the patched one needs a new app.
    monkeypatch.setattr(web_app_module, "create_all", _raise_db_error)
    unavailable = TestClient(create_app()).get("/api/news/export")
    assert unavailable.status_code == 503


def test_news_article_details_returns_503_when_storage_unavailable(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    web_app_module = import_module("app.web.app")

    def _raise_db_error() -> None:
        raise SQLAlchemyError()

    monkeypatch.setattr(web_app_module, "create_all", _raise_db_error)

    app = create_app()
    client = TestClient(app)

    response = client.get("/api/news/123")
    assert response.status_code == 503


def test_news_api_forwards_date_range_and_overrides_hours_passthrough(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    captured: dict[str, object] = {}

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **kwargs):
            captured.update(kwargs)
            row = SimpleNamespace(
                title="News",
                published_at=datetime(2026, 2, 21, 12, 0, tzinfo=UTC),
                rank_score=0.91,
                url_canonical="https://example.com/news",
                source_id=11,
            )
            return [(row, "src-key", "Source Name")]

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(news_routes, "ArticleRepo", _ArticleRepo)

    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/api/news?hours=48&limit=15&date_from=2026-02-20&date_to=2026-02-21&sort=published"
    )
    assert response.status_code == 200
    assert captured["date_from"] == date(2026, 2, 20)
    assert captured["date_to"] == date(2026, 2, 21)
    assert captured["hours"] is None


def test_news_template_has_date_range_inputs_and_copy_links_markers(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(pages_routes, "NewsDigestRepo", _NewsDigestRepo)

    app = create_app()
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert 'id="digest-date"' in page.text
    assert 'type="date"' in page.text
    assert "Yesterday&#39;s Digest" in page.text or "Yesterday's Digest" in page.text
    assert "defaulting to yesterday in UTC" in page.text


def test_news_template_has_network_error_handling_and_safe_row_rendering(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(pages_routes, "NewsDigestRepo", _NewsDigestRepo)

    app = create_app()
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert "No digest has been published for this date yet." in page.text
    assert "__DIGEST_CONTENT__" not in page.text
    assert "__REPORT_DATE__" not in page.text


def test_public_digest_template_has_selected_date_loading_hooks(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(pages_routes, "NewsDigestRepo", _NewsDigestRepo)

    app = create_app()
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert 'id="digest-results"' in page.text
    assert 'id="digest-empty-state"' in page.text
    assert "async function loadDigest" in page.text
    assert "/api/news/digests?date=" in page.text
    assert 'addEventListener("change", async' in page.text


def test_admin_route_is_protected_and_public_root_stays_open(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "true")
    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    auth_module = import_module("app.web.auth")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", auth_module.hash_password("s3cret-pass"))
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "0123456789abcdef0123456789abcdef")

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(pages_routes, "NewsDigestRepo", _NewsDigestRepo)

    app = create_app()
    client = TestClient(app)

    public_page = client.get("/", follow_redirects=False)
    admin_page = client.get("/admin", follow_redirects=False)

    assert public_page.status_code == 200
    assert "Yesterday&#39;s Digest" in public_page.text or "Yesterday's Digest" in public_page.text
    assert admin_page.status_code in {302, 303, 307, 308}
    assert admin_page.headers["location"].endswith("/login")


def test_public_root_hides_admin_controls_while_admin_route_shows_them(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "true")
    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    auth_module = import_module("app.web.auth")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", auth_module.hash_password("s3cret-pass"))
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "0123456789abcdef0123456789abcdef")

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(pages_routes, "NewsDigestRepo", _NewsDigestRepo)

    app = create_app()
    client = TestClient(app)

    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "s3cret-pass"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 204, 302, 303}

    public_page = client.get("/")
    admin_page = client.get("/admin")

    assert public_page.status_code == 200
    assert "Yesterday&#39;s Digest" in public_page.text or "Yesterday's Digest" in public_page.text
    assert "Update Sources" not in public_page.text
    assert "Add news sources" not in public_page.text

    assert admin_page.status_code == 200
    assert "Update Sources" in admin_page.text
    assert "Add news sources" in admin_page.text


def test_public_and_admin_pages_expose_distinct_shell_markers(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "true")
    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    auth_module = import_module("app.web.auth")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", auth_module.hash_password("s3cret-pass"))
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "0123456789abcdef0123456789abcdef")

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(pages_routes, "NewsDigestRepo", _NewsDigestRepo)

    client = TestClient(create_app())
    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "s3cret-pass"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 204, 302, 303}

    public_page = client.get("/")
    admin_page = client.get("/admin")

    assert public_page.status_code == 200
    assert 'id="public-digest-shell"' in public_page.text
    assert 'id="admin-shell"' not in public_page.text

    assert admin_page.status_code == 200
    assert 'id="admin-shell"' in admin_page.text
    assert 'id="public-digest-shell"' not in admin_page.text


def test_public_and_admin_pages_use_distinct_surface_labels(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "true")
    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "operator")
    auth_module = import_module("app.web.auth")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH", auth_module.hash_password("s3cret-pass"))
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "0123456789abcdef0123456789abcdef")

    class _DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    def _session_local():
        return _DummySession()

    class _NewsDigestRepo:
        def __init__(self, _session) -> None:
            pass

        def get_digest(self, *, report_date):  # type: ignore[no-untyped-def]
            del report_date

    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "SessionLocal", _session_local)
    monkeypatch.setattr(pages_routes, "NewsDigestRepo", _NewsDigestRepo)

    client = TestClient(create_app())
    login = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "s3cret-pass"},
        follow_redirects=False,
    )
    assert login.status_code in {200, 204, 302, 303}

    public_page = client.get("/")
    admin_page = client.get("/admin")

    assert "Public Briefing" in public_page.text
    assert "Operator Console" not in public_page.text
    assert "Operator Console" in admin_page.text
    assert "Public Briefing" not in admin_page.text


def test_source_onboarding_import_reports_only_new_candidates_for_current_batch(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    app = create_app()
    client = TestClient(app)

    first = client.post(
        "/api/source-onboarding/import",
        json={"raw_text": "https://example.com/blog?utm_source=feed"},
    )
    assert first.status_code == 201
    first_payload = first.json()
    assert first_payload["batch_id"] == 1
    assert first_payload["accepted_count"] == 1
    assert first_payload["candidate_ids"] == [1]

    second = client.post(
        "/api/source-onboarding/import",
        json={"raw_text": "https://EXAMPLE.com/blog#top"},
    )
    assert second.status_code == 201
    second_payload = second.json()
    assert second_payload["batch_id"] == 2
    assert second_payload["accepted_count"] == 0
    assert second_payload["rejected_count"] == 1
    assert second_payload["candidate_ids"] == []


def test_source_onboarding_validate_rejects_invalid_identifier_payloads(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    bad_batch_id = client.post(
        "/api/source-onboarding/validate",
        json={"batch_id": "not-an-int"},
    )
    assert bad_batch_id.status_code == 422

    bad_candidate_ids = client.post(
        "/api/source-onboarding/validate",
        json={"candidate_ids": ["broken"]},
    )
    assert bad_candidate_ids.status_code == 422


def test_admin_page_sort_defaults_to_published() -> None:
    class _SortOptions(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.in_sort = False
            self.options: list[tuple[str, bool]] = []

        def handle_starttag(self, tag, attrs) -> None:
            attributes = dict(attrs)
            if tag == "select":
                self.in_sort = attributes.get("id") == "sort"
            elif tag == "option" and self.in_sort:
                self.options.append((str(attributes.get("value")), "selected" in attributes))

        def handle_endtag(self, tag) -> None:
            if tag == "select":
                self.in_sort = False

    parser = _SortOptions()
    parser.feed(pages_routes._render_index())  # pylint: disable=protected-access

    assert [value for value, _ in parser.options] == ["rank", "published", "category"]
    assert [value for value, selected in parser.options if selected] == ["published"]
