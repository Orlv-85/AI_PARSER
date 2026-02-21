import time
from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import get_settings
from app.web.app import create_app


def test_web_app_pages_and_update_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    monkeypatch.setattr(
        "app.web.service.run_fetch_cycle",
        lambda **kwargs: SimpleNamespace(fetched=3, new=2, duplicates=1, errors=0),
    )

    app = create_app()
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert "Update" in page.text
    assert "View" in page.text

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
