import time
from datetime import UTC, date, datetime
from importlib import import_module
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import get_settings
from app.web.app import create_app


def test_web_app_pages_and_update_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    class _ArticleRepo:
        def __init__(self, _session) -> None:
            pass

        def list_for_view(self, **_kwargs):
            return []

    monkeypatch.setattr(
        "app.web.service.run_fetch_cycle",
        lambda **kwargs: SimpleNamespace(fetched=3, new=2, duplicates=1, errors=0),
    )
    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "create_all", lambda: None)
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

    app = create_app()
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert "Update" in page.text
    assert "View" in page.text
    assert "Import Source Candidates" in page.text
    assert 'id="onboarding-import-raw-text"' in page.text
    assert 'id="import-onboarding-batch"' in page.text
    assert "/api/source-onboarding/import" in page.text
    assert 'id="validate-onboarding-batch"' in page.text
    assert "/api/source-onboarding/validate" in page.text
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


def test_second_update_run_is_rejected_when_running(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    def _slow_cycle(**_kwargs):
        time.sleep(0.2)
        return SimpleNamespace(fetched=1, new=1, duplicates=0, errors=0)

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
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

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
            return None

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
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

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
            return None

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
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

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
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

    app = create_app()
    client = TestClient(app)

    ok = client.get("/api/news/export?date_from=2026-02-20&date_to=2026-02-21")
    assert ok.status_code == 200
    assert captured["hours"] is None
    assert captured["date_from"] == date(2026, 2, 20)
    assert captured["date_to"] == date(2026, 2, 21)

    def _raise_db_error() -> None:
        raise SQLAlchemyError()

    monkeypatch.setattr(web_app_module, "create_all", _raise_db_error)
    unavailable = client.get("/api/news/export")
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
    monkeypatch.setattr(web_app_module, "ArticleRepo", _ArticleRepo)

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
    app = create_app()
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert 'id="date_from"' in page.text
    assert 'id="date_to"' in page.text
    assert 'id="copy-links"' in page.text
    assert "navigator.clipboard.writeText" in page.text
    assert "copy visible links" in page.text.lower()


def test_news_template_has_network_error_handling_and_safe_row_rendering(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert "Unable to load news due to a network error. Please retry." in page.text
    assert "row.innerHTML" not in page.text
    assert "titleCell.textContent = item.title;" in page.text


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
