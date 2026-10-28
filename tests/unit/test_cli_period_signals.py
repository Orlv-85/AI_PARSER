import json
from datetime import UTC, datetime, timedelta

import pytest
from period_db import seed_weeks  # pylint: disable=import-error
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.config.settings import Settings
from app.core.periodic.period_run import first_week, latest_completed_week
from app.storage.models_sql import Base, PeriodSignalReport

TODAY = datetime.now(UTC).date()
LATEST = latest_completed_week(TODAY)
PREVIOUS = LATEST - timedelta(days=7)
FROM = PREVIOUS - timedelta(days=3)  # inside the week before the previous one
runner = CliRunner()


def make_factory(tmp_path, monkeypatch, *, enabled):
    engine = create_engine(f"sqlite:///{tmp_path / 'cli.db'}")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    monkeypatch.setattr(cli_main, "SessionLocal", maker)
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "get_settings", lambda: Settings(
        _env_file=None, daily_signals_comparable_from=FROM, period_signals_enabled=enabled))
    return engine, maker


def invoke(*args):
    result = runner.invoke(cli_main.app, ["period-signals", *args])
    return result.exit_code, result.output


def stored(maker):
    with maker() as session:
        return sorted(r.period_start for r in session.scalars(select(PeriodSignalReport)))


def test_flag_off_says_so_and_writes_nothing(tmp_path, monkeypatch):
    engine, maker = make_factory(tmp_path, monkeypatch, enabled=False)
    seed_weeks(maker, PREVIOUS, LATEST, comparable_from=FROM)
    code, output = invoke("--backfill", "2")
    assert code == 0
    assert json.loads(output)["state"] == "disabled"
    assert stored(maker) == []
    with maker() as session:
        assert session.scalar(select(func.count(PeriodSignalReport.id))) == 0
    engine.dispose()


def test_default_run_computes_the_latest_completed_week(tmp_path, monkeypatch):
    engine, maker = make_factory(tmp_path, monkeypatch, enabled=True)
    seed_weeks(maker, PREVIOUS, LATEST, comparable_from=FROM)
    code, output = invoke()
    assert code == 0
    report = json.loads(output)
    assert report["state"] == "ok" and report["written"] == [LATEST.isoformat()]
    assert stored(maker) == [LATEST]
    engine.dispose()


def test_backfill_period_and_recompute_all(tmp_path, monkeypatch):
    engine, maker = make_factory(tmp_path, monkeypatch, enabled=True)
    seed_weeks(maker, PREVIOUS, LATEST, comparable_from=FROM)
    assert first_week(FROM) == PREVIOUS
    code, output = invoke("--backfill", "5")
    report = json.loads(output)
    assert code == 0
    assert report["written"] == [PREVIOUS.isoformat(), LATEST.isoformat()]
    assert len(report["skipped_before_first"]) == 3
    assert stored(maker) == [PREVIOUS, LATEST]
    code, output = invoke("--period", PREVIOUS.isoformat())
    assert (code, json.loads(output)["unchanged"]) == (0, 1)
    code, output = invoke("--recompute-all")
    assert (code, json.loads(output)["written"]) == (0, [])
    engine.dispose()


def test_month_before_the_first_month_writes_nothing(tmp_path, monkeypatch):
    engine, maker = make_factory(tmp_path, monkeypatch, enabled=True)
    seed_weeks(maker, LATEST, comparable_from=FROM)
    code, output = invoke("--kind", "month")
    report = json.loads(output)
    assert (code, report["state"], report["written"]) == (0, "ok", [])
    assert report["kind"] == "month" and report["periods"] == {}
    assert stored(maker) == []
    engine.dispose()


def test_plain_run_adds_the_month_report_and_a_kind_does_not(tmp_path, monkeypatch):
    engine, maker = make_factory(tmp_path, monkeypatch, enabled=True)
    seed_weeks(maker, PREVIOUS, LATEST, comparable_from=FROM)
    plain = json.loads(invoke()[1])
    assert plain["kind"] == "week" and plain["written"] == [LATEST.isoformat()]
    assert plain["month"]["kind"] == "month" and plain["month"]["written"] == []
    assert "month" not in json.loads(invoke("--kind", "week")[1])
    assert "month" not in json.loads(invoke("--backfill", "2")[1])
    engine.dispose()


@pytest.mark.parametrize("args", [
    ["--kind", "year"], ["--period", "2026-13-01"], ["--period", TODAY.isoformat()],
    ["--period", (FROM - timedelta(days=30)).isoformat()], ["--backfill", "0"]])
def test_bad_arguments_exit_2(tmp_path, monkeypatch, args):
    engine, _ = make_factory(tmp_path, monkeypatch, enabled=True)
    assert invoke(*args)[0] == 2
    engine.dispose()
