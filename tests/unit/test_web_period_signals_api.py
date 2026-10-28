import json
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from period_fixtures import fixture_period_input  # pylint: disable=import-error
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.core.periodic.period_compute import compute_period
from app.storage.models_sql import Base, PeriodSignalReport
from app.web.app import create_app

W1, W2, W3 = date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26)


@pytest.fixture(name="client")
def client_fixture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path}/period-api.db", future=True)
    maker = sessionmaker(bind=engine, autoflush=False, future=True)
    web = import_module("app.web.app")
    monkeypatch.setattr(web, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web, "SessionLocal", maker)
    # Provider code must never run on a request: every paid call goes through the ledger.
    monkeypatch.setattr("app.storage.daily_signals_ledger.SignalsLedger.dispatch",
                        lambda *a, **k: pytest.fail("provider call"))
    yield TestClient(create_app()), maker, engine
    engine.dispose()
    get_settings.cache_clear()


def store(maker, engine, start, payload, *, status="ready", kind="week"):
    Base.metadata.create_all(bind=engine)
    now = datetime.now(UTC)
    with maker() as session:
        session.add(PeriodSignalReport(
            period_kind=kind, period_start=start, period_end=start, methodology_version="m",
            extraction_version="e", status=status, payload_hash="x" * 64, thresholds="{}",
            coverage="{}", payload=payload if isinstance(payload, str) else json.dumps(payload),
            created_at=now, updated_at=now))
        session.commit()


def computed(status=None, start=W1):
    payload = json.loads(json.dumps(compute_period(fixture_period_input())))
    payload["period_start"] = start.isoformat()
    payload["period_end"] = (start + timedelta(days=6)).isoformat()
    if status is not None:
        payload["status"] = status
    return payload


def test_ready_week(client):
    http, maker, engine = client
    store(maker, engine, W1, computed())
    body = http.get("/api/news/period-signals?kind=week&start=2026-10-12").json()
    assert body["status"] == "ready"
    assert (body["period_kind"], body["period_start"], body["period_end"]) == (
        "week", "2026-10-12", "2026-10-18")
    assert body["coverage"]["days"] == 7 and body["top_stories"]
    assert body["event_mix"]["types"] and body["brief"] is None


def test_partial_week_is_served_with_its_status(client):
    http, maker, engine = client
    store(maker, engine, W1, computed("partial"), status="partial")
    body = http.get("/api/news/period-signals?start=2026-10-12").json()
    assert body["status"] == "partial" and body["brief"] is None


def test_default_is_the_latest_ready_or_building_period(client):
    http, maker, engine = client
    store(maker, engine, W1, computed("building_history", W1), status="building_history")
    store(maker, engine, W2, computed(None, W2), status="ready")
    store(maker, engine, W3, computed("partial", W3), status="partial")
    assert http.get("/api/news/period-signals").json()["period_start"] == "2026-10-19"


def test_default_falls_back_to_a_partial_week(client):
    http, maker, engine = client
    store(maker, engine, W3, computed("partial", W3), status="partial")
    assert http.get("/api/news/period-signals").json()["status"] == "partial"


def test_missing_row_is_unavailable_200(client):
    http, _, _ = client
    for query in ("", "?start=2026-10-12", "?kind=month"):
        response = http.get("/api/news/period-signals" + query)
        assert response.status_code == 200
        body = response.json()
        assert (body["status"], body["top_stories"], body["brief"]) == ("unavailable", [], None)


@pytest.mark.parametrize("payload", ["{not json", "[]", json.dumps({"status": "weird"}),
                                     json.dumps({"period_kind": "week", "status": "ready",
                                                 "top_stories": "no"})])
def test_corrupt_row_is_unavailable_200(client, payload):
    http, maker, engine = client
    store(maker, engine, W1, payload)
    response = http.get("/api/news/period-signals?start=2026-10-12")
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["period_start"]) == ("unavailable", "2026-10-12")
    assert body["notes"] == ["Period signals could not be read."]


@pytest.mark.parametrize("query", ["?kind=year", "?start=yesterday"])
def test_invalid_query_is_422(client, query):
    http, _, _ = client
    assert http.get("/api/news/period-signals" + query).status_code == 422


def test_index_lists_newest_first_without_payloads(client):
    http, maker, engine = client
    store(maker, engine, W1, computed(), status="ready")
    store(maker, engine, W3, "{broken", status="partial")  # a broken payload does not matter
    store(maker, engine, W2, computed(), status="ready")
    body = http.get("/api/news/period-signals/index").json()
    assert [p["period_start"] for p in body["periods"]] == ["2026-10-26", "2026-10-19",
                                                            "2026-10-12"]
    assert body["periods"][0].keys() == {"period_kind", "period_start", "period_end", "status",
                                         "computed_at"}
    assert http.get("/api/news/period-signals/index?kind=month").json() == {"periods": []}


def test_empty_index(client):
    http, _, _ = client
    assert http.get("/api/news/period-signals/index").json() == {"periods": []}


def test_request_path_does_not_import_provider_code():
    source = Path(import_module("app.web.routes.period").__file__).read_text(encoding="utf-8")
    storage = Path(import_module("app.storage.period_signals").__file__).read_text(encoding="utf-8")
    for text in (source, storage):
        for name in ("httpx", "ledger", "signals_brief", "DS_API_KEY", "ds_api_key"):
            assert name not in text, name
