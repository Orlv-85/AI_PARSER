import json
import logging
from datetime import UTC, date, datetime
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.storage.models_sql import Base, DailySignalReport
from app.web.app import create_app

D = date(2026, 10, 16)
PAYLOAD = {
    "report_date": "2026-10-16", "status": "building_history",
    "methodology_version": "daily-signals-1", "extraction_version": "daily-signals-extract-5",
    "generated_at": "2026-10-17T02:30:00+00:00", "novelty_history_days": 6,
    "comparable_complete_days": 6,
    "coverage": {"items": 58, "matched": 58, "extracted": 58, "failed": 0, "skipped": 0,
                 "pending": 0, "unmatched": 0},
    "notes": [], "sections": {"new": {"state": "building", "note": "History: 6 complete days."}},
    "thresholds": {"new_max": 8},
    "new": [{"entity_id": 7, "name": "Glimpse", "type": "model", "vendor": "Elorian",
             "level": "early", "variant_of": None, "variants": [],
             "novelty_quote": "The model, Glimpse, is launching", "articles": 1, "publishers": 1,
             "links": [{"title": "Elorian releases Glimpse", "url": "https://t.com/g",
                        "publisher": "t.com"}]}],
    "top_stories": [], "rising": [], "cooling": [],
    "event_counts": [{"event_type": "model_release", "label": "model releases", "stories": 1,
                      "articles": 1, "links": []}],
    "article_event_types": {"https://t.com/g": "model_release"},
}


@pytest.fixture(name="client")
def client_fixture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path}/signals-api.db", future=True)
    maker = sessionmaker(bind=engine, autoflush=False, future=True)
    web = import_module("app.web.app")
    monkeypatch.setattr(web, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web, "SessionLocal", maker)
    # Provider code must never run on a request.
    monkeypatch.setattr("app.core.daily_signals.run_signals",
                        lambda *a, **k: pytest.fail("run_signals called"))
    monkeypatch.setattr("app.storage.daily_signals_ledger.SignalsLedger.dispatch",
                        lambda *a, **k: pytest.fail("provider call"))
    yield TestClient(create_app()), maker, engine
    engine.dispose()
    get_settings.cache_clear()


def store(maker, engine, payload):
    Base.metadata.create_all(bind=engine)
    with maker() as session:
        session.add(DailySignalReport(
            report_date=D, methodology_version="daily-signals-1",
            extraction_version="daily-signals-extract-5", status="building_history",
            payload_hash="x" * 64, thresholds="{}", coverage="{}",
            payload=payload if isinstance(payload, str) else json.dumps(payload),
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
        session.commit()


def test_stored_snapshot(client):
    http, maker, engine = client
    store(maker, engine, PAYLOAD)
    response = http.get("/api/news/daily-signals?date=2026-10-16")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "building_history"
    assert body["new"][0]["name"] == "Glimpse"
    assert body["sections"]["new"] == {"state": "building", "note": "History: 6 complete days."}
    assert body["coverage"]["items"] == 58


def test_missing_snapshot_is_unavailable(client):
    http, _, _ = client
    response = http.get("/api/news/daily-signals?date=2026-10-15")
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["new"], body["report_date"]) == ("unavailable", [], "2026-10-15")


@pytest.mark.parametrize("query", ["", "?date=2026-13-01", "?date=yesterday"])
def test_invalid_date_is_422(client, query):
    http, _, _ = client
    assert http.get("/api/news/daily-signals" + query).status_code == 422


def test_corrupt_payload_is_unavailable_with_note(client, caplog):
    http, maker, engine = client
    store(maker, engine, "{not json")
    with caplog.at_level(logging.ERROR):
        body = http.get("/api/news/daily-signals?date=2026-10-16").json()
    assert (body["status"], body["notes"]) == ("unavailable", ["Daily signals could not be read."])
    assert "daily_signals_payload_unreadable" in caplog.text
    with maker() as session:
        session.query(DailySignalReport).delete()
        session.commit()
    store(maker, engine, dict(PAYLOAD, status="weird"))
    assert http.get("/api/news/daily-signals?date=2026-10-16").json()["status"] == "unavailable"


def test_storage_error_is_503(client, monkeypatch):
    http, _, _ = client
    web = import_module("app.web.app")

    def broken():
        raise SQLAlchemyError("down")

    monkeypatch.setattr(web, "SessionLocal", broken)
    assert http.get("/api/news/daily-signals?date=2026-10-16").status_code == 503


def test_public_when_auth_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("AINEWS_AUTH_ENABLED", "true")
    monkeypatch.setenv("AINEWS_AUTH_USERNAME", "admin")
    monkeypatch.setenv("AINEWS_AUTH_PASSWORD_HASH",
                       "$2b$12$abcdefghijklmnopqrstuuuuuuuuuuuuuuuuuuuuuuuuuu")
    monkeypatch.setenv("AINEWS_AUTH_SECRET", "12345678901234567890123456789012")
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path}/auth.db", future=True)
    web = import_module("app.web.app")
    monkeypatch.setattr(web, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web, "SessionLocal", sessionmaker(bind=engine, future=True))
    http = TestClient(create_app())
    response = http.get("/api/news/daily-signals?date=2026-10-16", follow_redirects=False)
    assert response.status_code == 200 and response.json()["status"] == "unavailable"
    assert http.get("/api/update/settings", follow_redirects=False).status_code == 401
    engine.dispose()
    get_settings.cache_clear()


def test_digest_api_unchanged(client):
    http, _, _ = client
    body = http.get("/api/news/digests?date=2026-10-16").json()
    assert body == {"report_date": "2026-10-16", "groups": []}
