# pylint: disable=redefined-outer-name,unused-argument
import json
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

from app.cli import bulletin as cli_bulletin
from app.cli import deps as cli_deps
from app.cli import main as cli_main
from app.config.settings import Settings
from app.core.bulletin.world_change import ASSESS_DEFAULT_MAX_USD, WORLD_CHANGE_VERSION, WorldChange
from app.core.bulletin.writer import WRITER_MODEL, WRITER_VERSION
from app.core.canonicalize import canonical_url_hash
from app.storage.bulletin_store import BulletinRepo
from app.storage.digest_repo import NewsDigestRepo
from app.storage.models_sql import Article, Base, BulletinRow, DailySignalReport
from app.storage.world_change import WorldChangeRepo
from app.usecases.bulletin.writer_run import WRITER_MAX_USD_PER_DAY

DAY = date(2026, 10, 30)
TODAY = date(2026, 11, 2)
ANSWER = WorldChange("changed", 0.9, "Work", 0.8, "organisation", 0.8, 0.0)
NOTE = "The work now follows a different process."


@pytest.fixture
def daily(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(_env_file=None, jev_api_key="fake-jev", ds_api_key="fake-ds")
    calls = SimpleNamespace(assess=[], writer=[], assessor_days=[], writer_days=[])

    def assess(article):
        calls.assess.append(article.id)
        return ANSWER

    @contextmanager
    def assessor_factory(actual_settings, logger, target, max_usd):
        assert actual_settings is settings
        assert max_usd == ASSESS_DEFAULT_MAX_USD
        calls.assessor_days.append(target)
        yield SimpleNamespace(assess=assess, stopped=False, model="fake-jev",
                              payment_journal=None)

    def ask(body):
        calls.writer.append(body)
        content = {"headline": "AI changes the work", "stories": [{
            "id": "s1", "headline": "Work changes", "site": [NOTE],
            "telegram": [NOTE], "gloss": None}]}
        return {"model": WRITER_MODEL, "choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(content)}}]}, None

    @contextmanager
    def writer_factory(actual_settings, today, *, max_usd):
        assert actual_settings is settings
        assert max_usd == float(WRITER_MAX_USD_PER_DAY)
        calls.writer_days.append(today)
        yield SimpleNamespace(ask=ask, cost_usd=lambda: 0.001)

    monkeypatch.setattr(cli_deps, "SessionLocal", maker)
    monkeypatch.setattr(cli_deps, "create_all", lambda: Base.metadata.create_all(engine))
    monkeypatch.setattr(cli_deps, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_bulletin, "utc_today", lambda: TODAY)
    monkeypatch.setattr(cli_bulletin, "open_assessor", assessor_factory)
    monkeypatch.setattr(cli_bulletin, "open_writer", writer_factory)
    yield SimpleNamespace(maker=maker, settings=settings, calls=calls)
    engine.dispose()


def seed(daily, *, day=DAY, answered=False, status="ready"):
    with daily.maker() as session:
        url = "https://example.com/a"
        article = Article(title="AI changes the work", url=url, url_canonical=url,
                          url_canonical_hash=canonical_url_hash(url))
        session.add(article)
        session.flush()
        if answered:
            WorldChangeRepo(session).save(article, ANSWER, version=WORLD_CHANGE_VERSION,
                                          model="fake")
        NewsDigestRepo(session).save_digest(report_date=day, groups=[{"title": "G", "items": [
            {"title": article.title, "summary": "s", "url": url}]}])
        payload = {"status": status, "quiet": False, "coverage": {"items": 1},
                   "event_counts": [], "top_stories": []}
        session.add(DailySignalReport(
            report_date=day, methodology_version="m", extraction_version="e", status=status,
            payload_hash="h", thresholds="{}", payload=json.dumps(payload), coverage="{}"))
        session.commit()


def invoke(*args):
    return CliRunner().invoke(cli_main.app, ["bulletin", "daily", *args])


def run_day():
    result = invoke("--date", DAY.isoformat())
    assert result.exit_code == 0, result.output
    return result, json.loads(result.stdout)


def test_daily_assesses_builds_writes_and_stores(daily):
    seed(daily)
    result, summary = run_day()
    assert summary["date"] == DAY.isoformat()
    assert summary["status"] == "ready" and summary["reason"] is None
    assert summary["stored"] is True and summary["refused"] is False
    assert summary["assess"]["assessed"] == 1
    assert summary["writer"]["reason"] is None
    assert summary["writer"]["cost_usd"] == 0.001
    assert daily.calls.assessor_days == [DAY] and daily.calls.writer_days == [TODAY]
    assert len(daily.calls.assess) == len(daily.calls.writer) == 1
    with daily.maker() as session:
        row = BulletinRepo(session).get(DAY)
        assert row.status == "ready" and row.reason is None
        story = row.payload["key_results"][0]
        assert story["text_origin"] == "model" and story["site_note"] == [NOTE]
        assert row.numbers == {"assessed": 1, "digest_articles": 1, "writer": summary["writer"]}
        assert row.versions["writer"] == WRITER_VERSION
        assert session.scalar(select(func.count()).select_from(BulletinRow)) == 1
    _, repeated = run_day()
    assert repeated["assess"]["skipped"] == 1 and repeated["assess"]["assessed"] == 0
    assert len(daily.calls.assess) == 1
    assert "bulletin_assessed_share" in result.stderr


@pytest.mark.parametrize("key", [None, "   "])
def test_daily_without_ds_key_stores_title_only(daily, key):
    daily.settings.ds_api_key = None if key is None else SecretStr(key)
    seed(daily)
    result, summary = run_day()
    assert summary["writer"] == {"reason": "missing_ds_key"}
    assert not daily.calls.writer and "missing_ds_key" in result.stderr
    with daily.maker() as session:
        row = BulletinRepo(session).get(DAY)
        assert row.status == "ready" and row.payload["key_results"][0]["text_origin"] == "title"
        assert "writer" not in row.versions and "writer" not in row.numbers


@pytest.mark.parametrize("key", [None, "   "])
def test_daily_without_jev_key_builds_from_stored_answers(daily, key):
    daily.settings.jev_api_key = None if key is None else SecretStr(key)
    seed(daily, answered=True)
    result, summary = run_day()
    assert summary["assess"] == {"reason": "missing_jev_key"}
    assert not daily.calls.assessor_days and "missing_jev_key" in result.stderr
    assert summary["status"] == "ready" and summary["stored"] is True
    assert len(daily.calls.writer) == 1


@pytest.mark.parametrize("reason,status", [
    ("no_assessments", "ready"), ("signals_partial", "partial"),
    ("no_signals", None), ("no_digest", "absent")])
def test_daily_skipped_day_is_stored(daily, reason, status):
    daily.settings.jev_api_key = None
    if status != "absent":
        seed(daily, status=status or "ready")
    if status is None:
        with daily.maker() as session:
            session.query(DailySignalReport).delete()
            session.commit()
    _, summary = run_day()
    assert summary["status"] == "skipped" and summary["reason"] == reason
    assert summary["writer"] == {"reason": reason}
    assert summary["stored"] is True and summary["refused"] is False
    assert not daily.calls.writer_days
    with daily.maker() as session:
        row = BulletinRepo(session).get(DAY)
        assert row.status == "skipped" and row.reason == reason and row.payload == {}


def test_daily_posted_day_is_refused_and_exits_zero(daily):
    seed(daily)
    run_day()
    with daily.maker() as session:
        row = BulletinRepo(session).get(DAY)
        row.telegram_message_id = 42
        before = (row.payload, row.numbers, row.generated_at)
        session.commit()
    result, summary = run_day()
    assert summary["stored"] is False and summary["refused"] is True
    assert '"refused": true' in result.stderr
    with daily.maker() as session:
        row = BulletinRepo(session).get(DAY)
        assert (row.payload, row.numbers, row.generated_at) == before
        assert row.telegram_message_id == 42


def test_daily_defaults_to_yesterday_utc(daily):
    yesterday = date(2026, 11, 1)
    seed(daily, day=yesterday)
    result = invoke()
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["date"] == yesterday.isoformat()
    assert daily.calls.assessor_days == [yesterday]
    assert daily.calls.writer_days == [TODAY]


def test_daily_writer_uses_current_utc_day_after_assessment(daily, monkeypatch):
    seed(daily)
    clock = iter([DAY, TODAY])
    monkeypatch.setattr(cli_bulletin, "utc_today", lambda: next(clock))
    _, summary = run_day()
    assert summary["stored"] is True and daily.calls.writer_days == [TODAY]


def test_daily_missing_digest_with_keys_is_skipped(daily):
    _, summary = run_day()
    assert summary["assess"] == {"reason": "no_digest"}
    assert summary["reason"] == "no_digest" and summary["stored"] is True
    assert not daily.calls.assess and not daily.calls.writer_days
    with daily.maker() as session:
        assert BulletinRepo(session).get(DAY).numbers == {"assessed": 0, "digest_articles": 0}


def test_daily_shared_assessment_dry_run_is_read_only(daily):
    seed(daily)
    daily.settings.jev_api_key = None
    result = CliRunner().invoke(cli_main.app, [
        "bulletin", "assess", "--date", DAY.isoformat(), "--dry-run"])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["dry_run"] is True and summary["would_assess"] == 1
    assert not daily.calls.assessor_days
    with daily.maker() as session:
        assert WorldChangeRepo(session).answered([canonical_url_hash("https://example.com/a")],
                                                WORLD_CHANGE_VERSION) == set()


def test_daily_prints_one_summary_line(daily):
    seed(daily)
    result, summary = run_day()
    assert len(result.stdout.splitlines()) == 1
    assert set(summary) == {"date", "status", "reason", "assess", "writer", "stored", "refused"}


def test_daily_invalid_date_is_a_usage_error(daily):
    result = invoke("--date", "2026-02-30")
    assert result.exit_code == 2
    assert not daily.calls.assess and not daily.calls.writer
    assert result.stdout == "" and "YYYY-MM-DD" in result.stderr


@pytest.mark.parametrize("detail", ["journal directory read-only", "x" * 201])
def test_daily_runtime_failure_exits_zero(daily, monkeypatch, detail):
    def fail():
        raise OSError(detail)

    monkeypatch.setattr(cli_deps, "create_all", fail)
    result, summary = run_day()
    assert summary["reason"] == "daily_failed"
    assert summary["stored"] is False and summary["refused"] is False
    event = next(event for event in map(json.loads, result.stderr.splitlines())
                 if event["message"] == "bulletin_daily_failed")
    assert event["date"] == DAY.isoformat()
    assert event["error"] == "OSError" and event["detail"] == detail[:200]
    assert event["level"] == "ERROR"


def test_bulletin_switches_default_off(monkeypatch):
    monkeypatch.delenv("AINEWS_BULLETIN_HOME_PAGE", raising=False)
    monkeypatch.delenv("AINEWS_BULLETIN_POST_CHANNELS", raising=False)
    settings = Settings(_env_file=None)
    assert settings.bulletin_home_page is False and settings.bulletin_post_channels is False


def test_bulletin_switches_read_environment(monkeypatch):
    monkeypatch.setenv("AINEWS_BULLETIN_HOME_PAGE", "true")
    monkeypatch.setenv("AINEWS_BULLETIN_POST_CHANNELS", "true")
    settings = Settings(_env_file=None)
    assert settings.bulletin_home_page is True and settings.bulletin_post_channels is True
