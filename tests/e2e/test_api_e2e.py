import time
from datetime import UTC, datetime
from importlib import import_module

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.config.sources import SourceConfig
from app.core.models import Article
from app.storage.models_sql import Base
from app.web.app import create_app


def test_api_e2e_update_and_read_news(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AINEWS_SOURCES_PATH", str(tmp_path / "sources.yaml"))
    monkeypatch.setenv("AINEWS_DATABASE_URL", f"sqlite:///{tmp_path}/e2e.db")
    get_settings.cache_clear()

    source_config = SourceConfig(
        id="e2e_rss",
        name="E2E RSS",
        type="rss",
        url="https://example.com/feed.xml",
        enabled=True,
        fetch_interval_minutes=30,
        source_weight=1.0,
    )

    def _fake_fetch_rss(_source_key: str, *_args, **_kwargs):
        return [
            Article(
                source_key="e2e_rss",
                title="E2E AI Update",
                url="https://example.com/e2e-ai-update",
                published_at=datetime.now(UTC),
                summary="E2E summary",
                content="E2E content",
            )
        ]

    monkeypatch.setattr("app.core.pipeline.fetch_rss", _fake_fetch_rss)
    monkeypatch.setattr("app.core.pipeline.load_sources", lambda _path: [source_config])

    engine = create_engine(f"sqlite:///{tmp_path}/e2e.db", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _create_all_local() -> None:
        Base.metadata.create_all(bind=engine)

    monkeypatch.setattr("app.core.pipeline.SessionLocal", session_local)
    monkeypatch.setattr("app.core.pipeline.create_all", _create_all_local)
    web_app_module = import_module("app.web.app")
    monkeypatch.setattr(web_app_module, "SessionLocal", session_local)
    monkeypatch.setattr(web_app_module, "create_all", _create_all_local)

    app = create_app()
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    start = client.post("/api/update/run")
    assert start.status_code == 200
    assert start.json()["status"] == "running"

    terminal = None
    for _ in range(50):
        status = client.get("/api/update/status")
        assert status.status_code == 200
        payload = status.json()
        if payload["status"] in {"finished", "failed"}:
            terminal = payload
            break
        time.sleep(0.02)

    assert terminal is not None
    assert terminal["status"] == "finished"
    assert terminal["fetched"] == 1
    assert terminal["new"] + terminal["duplicates"] == 1
    assert terminal["errors"] == 0

    news = client.get("/api/news?hours=24&limit=10")
    assert news.status_code == 200
    items = news.json()
    assert items
    assert items[0]["title"] == "E2E AI Update"
    assert items[0]["source_key"] == "e2e_rss"
    assert items[0]["source_name"] == "E2E RSS"
