"""Period brief (017 R4): the run, the nightly default, the command, the page and the API."""
# run_periods starts the report with "brief": None; pylint infers only that literal.
# pylint: disable=unsubscriptable-object
import json
from datetime import date, timedelta
from importlib import import_module

import pytest
from fastapi.testclient import TestClient
from period_brief_db import (  # pylint: disable=import-error
    PRO,
    WEEK_START,
    Provider,
    period_payload,
    store_digest,
    store_period,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.config.settings import Settings, get_settings
from app.core.periodic import period_run
from app.core.periodic.period_run import PeriodRunOptions, brief_targets, run_periods
from app.storage.models_sql import Base, PeriodSignalBrief, PeriodSignalReport
from app.web.app import create_app

W1 = date(2026, 10, 12)
NOW = period_run.datetime(2026, 10, 28, 3, 0)  # latest completed week starts 2026-10-19
FROM = date(2026, 10, 10)
runner = CliRunner()


@pytest.fixture(name="maker")
def maker_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_API_KEY", "secret-key")
    engine = create_engine(f"sqlite:///{tmp_path / 'flow.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(period_run, "compute_period", lambda data: period_payload(
        data.kind, data.start, status="ready"))
    yield sessionmaker(bind=engine)
    engine.dispose()


def settings(*, brief=True, **kwargs):
    return Settings(_env_file=None, daily_signals_comparable_from=FROM,
                    period_signals_enabled=True, period_signals_brief_enabled=brief, **kwargs)


def run(maker, tmp_path, provider, *, brief=True, **options):
    options.setdefault("cache_dir", tmp_path / "cache")
    with maker() as session:
        return run_periods(session, settings(brief=brief), PeriodRunOptions(**options), now=NOW,
                           transport=provider.transport)


def seed_weeks(maker, *starts):
    for start in starts:
        store_digest(maker, period_payload(start=start))


def briefs(maker):
    with maker() as session:
        return {r.period_start: r.status for r in session.scalars(select(PeriodSignalBrief))}


def test_targets_nightly_default_and_with_brief():
    options = PeriodRunOptions(backfill=3)
    weeks = [date(2026, 10, 5), W1, WEEK_START]
    assert brief_targets(options, weeks, today=NOW.date()) == [WEEK_START]
    assert not brief_targets(options, weeks[:2], today=NOW.date())
    assert brief_targets(PeriodRunOptions(with_brief=True), weeks, today=NOW.date()) == weeks


def test_flag_off_creates_no_provider_and_no_brief(maker, tmp_path, monkeypatch):
    seed_weeks(maker, WEEK_START)
    monkeypatch.setattr("app.core.periodic.period_brief_run.SignalsLedger",
                        lambda *a, **k: pytest.fail("provider object created"))
    provider = Provider()
    report = run(maker, tmp_path, provider, brief=False)
    assert report["brief"] is None and report["written"] == ["2026-10-19"]
    flagged = run(maker, tmp_path, provider, brief=False, with_brief=True)
    assert flagged["brief"]["state"] == "disabled"
    assert not provider.requests and briefs(maker) == {}


def test_nightly_default_briefs_the_latest_week_once(maker, tmp_path):
    seed_weeks(maker, W1, WEEK_START)
    provider = Provider()
    report = run(maker, tmp_path, provider, backfill=2)
    assert report["brief"]["periods"] == {"week:2026-10-19": "ok"}
    assert report["periods"]["2026-10-12"]["status"] == "ready" and len(provider.requests) == 1
    assert briefs(maker) == {WEEK_START: "ok"}
    again = run(maker, tmp_path, provider, backfill=2)
    assert not again["written"] and again["brief"]["periods"] == {"week:2026-10-19": "cached"}
    assert len(provider.requests) == 1


def test_with_brief_covers_every_week_of_the_run_within_the_cap(maker, tmp_path):
    seed_weeks(maker, W1, WEEK_START)
    provider = Provider()
    report = run(maker, tmp_path, provider, backfill=2, with_brief=True, max_usd="0.05")
    assert report["brief"]["periods"] == {"week:2026-10-12": "ok", "week:2026-10-19": "ok"}
    assert report["brief"]["run"]["usd"] == pytest.approx(2 * (3000 * 1.32 + 400 * 3.96) / 1e6)
    assert briefs(maker) == {W1: "ok", WEEK_START: "ok"}


def test_run_cap_max_usd_stops_the_step(maker, tmp_path):
    seed_weeks(maker, W1, WEEK_START)
    provider = Provider()
    report = run(maker, tmp_path, provider, backfill=2, with_brief=True, max_usd="0.001")
    assert report["brief"]["run"] == {"calls": 0, "usd": 0.0}
    assert set(report["brief"]["periods"].values()) <= {
        "skipped:cap_reached", "skipped:brief_budget_exhausted"}
    assert not provider.requests and briefs(maker) == {}


def test_a_brief_failure_keeps_the_numbers(maker, tmp_path, monkeypatch):
    seed_weeks(maker, WEEK_START)

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(period_run, "run_briefs", boom)
    report = run(maker, tmp_path, Provider())
    assert report["state"] == "ok" and report["written"] == ["2026-10-19"]
    assert report["brief"]["terminal_reason"] == "error:RuntimeError"
    with maker() as session:
        assert session.scalar(select(PeriodSignalReport)) is not None


# Command --------------------------------------------------------------------------------------
def cli_env(maker, monkeypatch, *, brief=True):
    monkeypatch.setattr(cli_main, "SessionLocal", maker)
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "get_settings", lambda: settings(brief=brief))
    monkeypatch.setattr(cli_main, "run_periods", lambda session, config, options, **kw: run_periods(
        session, config, options, now=NOW, transport=PROVIDER.transport))


PROVIDER = Provider()


def invoke(*args):
    result = runner.invoke(cli_main.app, ["period-signals", *args])
    return result.exit_code, result.output


def test_command_options_pass_to_the_run(maker, tmp_path, monkeypatch):
    seed_weeks(maker, W1, WEEK_START)
    PROVIDER.requests.clear()
    cli_env(maker, monkeypatch)
    code, output = invoke("--backfill", "2", "--with-brief", "--max-usd", "0.05",
                          "--cache-dir", str(tmp_path / "cli-cache"))
    report = json.loads(output)
    assert code == 0 and set(report["brief"]["periods"].values()) == {"ok"}
    assert len(PROVIDER.requests) == 2 and (tmp_path / "cli-cache" / "ledger.sqlite3").exists()


def test_command_rejects_a_bad_max_usd_and_flag_off_stays_disabled(maker, tmp_path, monkeypatch):
    cli_env(maker, monkeypatch)
    assert invoke("--max-usd", "0")[0] == 2
    assert invoke("--max-usd", "lots")[0] == 2
    monkeypatch.setattr(cli_main, "get_settings", lambda: Settings(
        _env_file=None, daily_signals_comparable_from=FROM, period_signals_enabled=False,
        period_signals_brief_enabled=True))
    code, output = invoke("--with-brief", "--cache-dir", str(tmp_path / "off"))
    assert code == 0 and json.loads(output)["state"] == "disabled"
    assert not (tmp_path / "off").exists()


# Page and API ---------------------------------------------------------------------------------
@pytest.fixture(name="client")
def client_fixture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path}/brief-page.db", future=True)
    maker = sessionmaker(bind=engine, autoflush=False, future=True)
    web = import_module("app.web.app")
    monkeypatch.setattr(web, "create_all", lambda: Base.metadata.create_all(bind=engine))
    monkeypatch.setattr(web, "SessionLocal", maker)
    monkeypatch.setattr("app.storage.daily_signals_ledger.SignalsLedger.dispatch",
                        lambda *a, **k: pytest.fail("provider call"))
    Base.metadata.create_all(bind=engine)
    yield TestClient(create_app(), follow_redirects=False), maker
    engine.dispose()
    get_settings.cache_clear()


def add_brief(maker, sentences, *, status="ok", start=WEEK_START):
    with maker() as session:
        session.add(PeriodSignalBrief(
            period_kind="week", period_start=start, brief_version="period-signals-brief-1",
            model=PRO, input_hash="h" * 64, status=status,
            payload=json.dumps({"sentences": sentences}) if status == "ok" else "{}"))
        session.commit()


def sentence(text, *urls):
    return {"text": text, "quote": "q", "links": [
        {"title": f"T{i}", "url": url, "publisher": "p"} for i, url in enumerate(urls)]}


def test_page_and_api_without_a_brief(client):
    http, maker = client
    store_period(maker, period_payload(), digest=False)
    assert http.get("/api/news/period-signals?start=2026-10-19").json()["brief"] is None
    html = http.get("/weekly").text
    assert "In brief" not in html and "Written by AI" not in html


def test_page_and_api_with_a_brief_on_top(client):
    http, maker = client
    store_period(maker, period_payload(), digest=False)
    add_brief(maker, [sentence("Acme launched Atlas.", "https://a.example.com/x", "ftp://bad/y"),
                      sentence("Borealis shipped.", "https://b.example.com/x")])
    body = http.get("/api/news/period-signals?start=2026-10-19").json()
    assert body["brief"]["model"] == PRO
    assert [s["text"] for s in body["brief"]["sentences"]] == [
        "Acme launched Atlas.", "Borealis shipped."]
    assert body["brief"]["sentences"][0]["links"][0]["url"] == "https://a.example.com/x"
    default = http.get("/api/news/period-signals").json()
    assert default["brief"]["sentences"][1]["text"] == "Borealis shipped."
    html = http.get("/weekly").text
    assert html.index("In brief") < html.index('id="period-stories"')
    assert html.index("In brief") < html.index("signals-status")
    assert "Written by AI from the linked articles; check the sources." in html
    assert 'href="https://a.example.com/x"' in html and "[1]" in html
    assert "ftp://bad/y" not in html


def test_brief_text_is_escaped_and_only_http_links_are_rendered(client):
    http, maker = client
    store_period(maker, period_payload(), digest=False)
    add_brief(maker, [sentence("<script>alert(1)</script> & more", "javascript:alert(1)",
                               'https://a.example.com/x?a="b"&c=<d>')])
    html = http.get("/weekly").text
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more" in html
    assert "javascript:alert" not in html and "[2]" not in html
    assert 'href="https://a.example.com/x?a=&quot;b&quot;&amp;c=&lt;d&gt;"' in html


def test_an_invalid_or_unreadable_brief_shows_nothing(client):
    http, maker = client
    store_period(maker, period_payload(), digest=False)
    add_brief(maker, [], status="invalid")
    assert http.get("/api/news/period-signals?start=2026-10-19").json()["brief"] is None
    assert "In brief" not in http.get("/weekly").text
    with maker() as session:
        row = session.scalar(select(PeriodSignalBrief))
        row.status, row.payload = "ok", "not json"
        session.commit()
    assert http.get("/api/news/period-signals?start=2026-10-19").json()["brief"] is None
    assert http.get("/weekly").status_code == 200


def test_the_brief_belongs_to_its_week(client):
    http, maker = client
    store_period(maker, period_payload(), digest=False)
    store_period(maker, period_payload(start=WEEK_START + timedelta(days=7)), digest=False)
    add_brief(maker, [sentence("Only this week.", "https://a.example.com/x")], start=WEEK_START)
    other = http.get("/api/news/period-signals?start=2026-10-26").json()
    assert other["brief"] is None
    assert "In brief" not in http.get("/weekly?week=2026-10-26").text
    assert "In brief" in http.get("/weekly?week=2026-10-19").text
