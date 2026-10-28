"""The /weekly page and its links (017 R3): states, escaping, ?week=, nav link, line on `/`."""
import json
from datetime import timedelta
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from test_web_period_signals_api import W1, W2, W3, computed, store  # pylint: disable=import-error

from app.config.settings import get_settings
from app.storage.models_sql import Base
from app.web.app import create_app
from app.web.period_view import week_label


@pytest.fixture(name="client")
def client_fixture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path}/period-page.db", future=True)
    maker = sessionmaker(bind=engine, autoflush=False, future=True)
    web = import_module("app.web.app")
    monkeypatch.setattr(web, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web, "SessionLocal", maker)
    monkeypatch.setattr("app.storage.daily_signals_ledger.SignalsLedger.dispatch",
                        lambda *a, **k: pytest.fail("provider call"))
    yield TestClient(create_app(), follow_redirects=False), maker, engine
    engine.dispose()
    get_settings.cache_clear()


def test_ready_week_shows_sections_in_order(client):
    http, maker, engine = client
    store(maker, engine, W1, computed())
    html = http.get("/weekly").text
    ids = ["period-stories", "period-entities", "period-new", "period-trends", "period-events"]
    assert [html.index(f'id="{i}"') for i in ids] == sorted(html.index(f'id="{i}"') for i in ids)
    assert "Week of Oct 12-18, 2026" in html and "7 of 7 days complete" in html
    assert 'href="/?date=2026-10-' in html
    assert "<style>" not in html and 'rel="stylesheet" href="/static/css/period.css"' in html


def test_building_history_says_first_week(client):
    http, maker, engine = client
    payload = computed("building_history")
    payload["comparison"] = {"state": "none", "reason": "no_previous_period"}
    payload["sections"]["rising"] = payload["sections"]["cooling"] = "hidden"
    store(maker, engine, W1, payload, status="building_history")
    html = http.get("/weekly").text
    assert "First week, no comparison with a previous week." in html
    assert 'id="period-rising"' not in html and "Rising and Cooling" in html


def test_suppressed_comparison_gives_a_reason_not_a_chart(client):
    http, maker, engine = client
    payload = computed()
    payload["comparison"] = {"state": "suppressed", "reason": "low_publisher_coverage"}
    payload["sections"]["rising"] = payload["sections"]["cooling"] = "hidden"
    payload["rising"] = payload["cooling"] = []
    for row in payload["event_mix"]["types"]:
        row["delta"] = row["previous_stories"] = None
    store(maker, engine, W1, payload)
    html = http.get("/weekly").text
    assert "low publisher coverage" in html and 'id="period-rising"' not in html
    assert "vs previous week" not in html


def test_partial_and_quiet_lines(client):
    http, maker, engine = client
    payload = computed("partial")
    payload["quiet"] = True
    store(maker, engine, W1, payload, status="partial")
    html = http.get("/weekly").text
    assert "Partial week" in html and "Quiet week: only" in html and "(partial)" in html


def test_no_rows_is_unavailable_200(client):
    http, _, _ = client
    response = http.get("/weekly")
    assert response.status_code == 200
    assert "Weekly signals are not available yet." in response.text
    assert "period-picker" not in response.text


@pytest.mark.parametrize("payload", ["not json", "[1, 2]", '{"status": "ready"}',
                                     '{"period_kind": "week", "status": "ready", '
                                     '"top_stories": [3, "x"], "new": [null], '
                                     '"event_mix": {"types": 5}, "coverage": {"days": "x"}}'])
def test_corrupt_row_is_200(client, payload):
    http, maker, engine = client
    store(maker, engine, W1, payload)
    response = http.get("/weekly?week=2026-10-12")
    assert response.status_code == 200
    assert "Weekly AI Signals" in response.text


def test_text_is_escaped_and_only_http_links(client):
    http, maker, engine = client
    payload = computed()
    bad = '<script>alert(1)</script>'
    payload["top_stories"][0]["label"] = bad
    payload["top_stories"][0]["links"] = [
        {"title": bad, "url": "javascript:alert(1)", "publisher": "x"},
        {"title": bad, "url": 'https://ok.example/a"b', "publisher": bad}]
    payload["new"] = [{"name": bad, "level": "early", "publishers": 1, "first_seen_day": bad,
                       "links": [{"title": "t", "url": "data:text/html,x", "publisher": "p"}]}]
    store(maker, engine, W1, payload)
    html = http.get("/weekly").text
    assert bad not in html and "&lt;script&gt;" in html
    assert "javascript:" not in html and "data:text" not in html
    assert 'href="https://ok.example/a&quot;b"' in html


def test_week_param(client):
    http, maker, engine = client
    store(maker, engine, W1, computed(None, W1))
    store(maker, engine, W2, computed(None, W2))
    assert "Week of Oct 12-18" in http.get("/weekly?week=2026-10-12").text
    moved = http.get("/weekly?week=2026-10-14")
    assert moved.status_code == 303 and moved.headers["location"] == "/weekly?week=2026-10-12"
    for odd in ("2026-10-26", "garbage"):
        response = http.get(f"/weekly?week={odd}")
        assert response.status_code in (200, 303)
    missing = http.get("/weekly?week=2026-10-26")
    assert "not available for this week" in missing.text and "period-picker" in missing.text
    assert "not available for this week" in http.get("/weekly?week=garbage").text
    latest = http.get("/weekly").text
    assert "Week of Oct 19-25" in latest and 'rel="prev" href="/weekly?week=2026-10-12"' in latest
    assert 'rel="next"' not in latest
    assert 'rel="next" href="/weekly?week=2026-10-19"' in http.get("/weekly?week=2026-10-12").text


def test_default_skips_a_newer_partial_week(client):
    http, maker, engine = client
    store(maker, engine, W2, computed(None, W2))
    store(maker, engine, W3, computed("partial", W3), status="partial")
    assert "Week of Oct 19-25" in http.get("/weekly").text


def test_week_label_across_months():
    assert week_label(W3, W3 + timedelta(days=6)) == "Oct 26 - Nov 1"


def test_nav_link_and_home_line_follow_stored_weeks(client):
    http, maker, engine = client
    empty = http.get("/?date=2026-10-16").text
    assert 'href="/weekly"' not in empty and "weekly signals" not in empty
    store(maker, engine, W1, computed(None, W1))
    store(maker, engine, W2, computed(None, W2))
    html = http.get("/?date=2026-10-16").text
    assert '<a class="hero-link" href="/weekly">Weekly</a>' in html
    assert "Week of Oct 19-25: weekly signals" in html
    assert html.index('id="daily-signals"') < html.index("Week of Oct 19-25")
    assert html.index("Week of Oct 19-25") < html.index('class="digest-shell"')


def test_home_page_survives_a_period_read_failure(client, monkeypatch):
    http, _, _ = client
    monkeypatch.setattr("app.web.routes.period.PeriodSignalRepo.index",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    response = http.get("/?date=2026-10-16")
    assert response.status_code == 200 and 'href="/weekly"' not in response.text
    assert json.loads('"ok"') == "ok"
