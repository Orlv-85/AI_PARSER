import json
from datetime import date, timedelta

import pytest
from period_db import (  # pylint: disable=import-error
    COMPARABLE_FROM,
    NOW,
    seed_day,
    seed_weeks,
)
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.core.periodic.period_run import (
    PeriodRunError,
    PeriodRunOptions,
    first_week,
    latest_completed_week,
    run_periods,
    target_weeks,
)
from app.storage.daily_signals import DailySignalRepo
from app.storage.models_sql import Base, PeriodSignalReport
from app.storage.period_signals import PeriodSignalRepo

W1, W2 = date(2026, 10, 12), date(2026, 10, 19)


@pytest.fixture(name="maker")
def maker_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'period.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


def settings(**kwargs):
    return Settings(_env_file=None, daily_signals_comparable_from=COMPARABLE_FROM,
                    period_signals_enabled=True, **kwargs)


def run(maker, **kwargs):
    with maker() as session:
        return run_periods(session, settings(), PeriodRunOptions(**kwargs), now=NOW)


def test_first_and_latest_week_bounds():
    assert first_week(date(2026, 10, 10)) == W1  # a Saturday: the next Monday
    assert first_week(date(2026, 10, 12)) == W1  # a Monday: itself
    assert latest_completed_week(date(2026, 10, 26)) == date(2026, 10, 19)  # Monday: week ended
    assert latest_completed_week(date(2026, 10, 25)) == date(2026, 10, 12)  # Sunday: not yet
    assert latest_completed_week(NOW.date()) == W2


def test_targets_default_backfill_and_clipping_before_the_first_week():
    kwargs = {"today": NOW.date(), "comparable_from": COMPARABLE_FROM}
    assert target_weeks(PeriodRunOptions(), **kwargs) == ([W2], [])
    assert target_weeks(PeriodRunOptions(backfill=3), **kwargs) == (
        [W1, W2], [date(2026, 10, 5)])
    assert target_weeks(PeriodRunOptions(recompute_all=True), **kwargs) == ([W1, W2], [])
    assert target_weeks(PeriodRunOptions(period=date(2026, 10, 14)), **kwargs) == ([W1], [])


@pytest.mark.parametrize("period", [date(2026, 10, 26), date(2026, 10, 28), date(2026, 10, 7)])
def test_uncompleted_or_early_period_is_refused(period):
    with pytest.raises(PeriodRunError):
        target_weeks(PeriodRunOptions(period=period), today=NOW.date(),
                     comparable_from=COMPARABLE_FROM)


def test_run_round_trip_stores_oldest_first_and_links_the_previous_week(maker):
    seed_weeks(maker, W1, W2)
    report = run(maker, backfill=2)
    assert report["state"] == "ok"
    assert report["written"] == ["2026-10-12", "2026-10-19"]
    with maker() as session:
        repo = PeriodSignalRepo(session, comparable_from=COMPARABLE_FROM)
        first, second = repo.get_report("week", W1), repo.get_report("week", W2)
        assert (first.period_end, first.methodology_version) == (date(2026, 10, 18),
                                                                 "period-signals-1")
        payload = json.loads(second.payload)
        assert payload["period_start"] == "2026-10-19"
        assert payload["coverage"]["days"] == 7
        assert first.status == "partial"  # 21 items: below the weekly minimum
        assert payload["comparison"]["state"] == "none"  # a partial week is not a previous period
        assert json.loads(first.payload)["comparison"]["state"] == "none"
        assert repo.latest("week").period_start == W2
        assert [r.period_start for r in repo.index("week")] == [W2, W1]
        assert repo.previous("week", W2).status == first.status


def test_second_run_writes_nothing(maker):
    seed_weeks(maker, W1, W2)
    run(maker, backfill=2)
    with maker() as session:
        stamps = {r.period_start: (r.updated_at, r.payload_hash)
                  for r in session.scalars(select(PeriodSignalReport))}
    again = run(maker, backfill=2)
    assert (again["written"], again["unchanged"]) == ([], 2)
    again_all = run(maker, recompute_all=True)
    assert (again_all["written"], again_all["unchanged"]) == ([], 2)
    with maker() as session:
        assert stamps == {r.period_start: (r.updated_at, r.payload_hash)
                          for r in session.scalars(select(PeriodSignalReport))}


def test_changed_input_rewrites_only_that_period(maker):
    seed_weeks(maker, W1, W2)
    run(maker, backfill=2)
    seed_day(maker, W2 + timedelta(days=1), names=("Delta", "Echo", "Foxtrot", "Golf"))
    with maker() as session:
        DailySignalRepo(session, comparable_from=COMPARABLE_FROM).recompute_reports(
            W2 + timedelta(days=6), now=NOW)
        session.commit()
    again = run(maker, backfill=2)
    assert again["written"] == ["2026-10-19"]


def test_month_and_flag_off_do_nothing(maker):
    seed_weeks(maker, W1, W2)
    assert run(maker, kind="month")["state"] == "not_built"
    with maker() as session:
        off = run_periods(session, Settings(_env_file=None, period_signals_enabled=False),
                          PeriodRunOptions(), now=NOW)
    assert off["state"] == "disabled"
    with maker() as session:
        assert session.scalar(select(func.count(PeriodSignalReport.id))) == 0


def test_a_period_run_writes_only_period_signal_tables(maker):
    seed_weeks(maker, W1, W2)
    written: set[str] = set()

    def watch(_conn, _cursor, statement, *_rest):
        head = statement.lstrip().split(None, 3)
        if head[0].upper() == "INSERT":
            written.add(head[2].strip('"`'))
        elif head[0].upper() == "UPDATE":
            written.add(head[1].strip('"`'))
        elif head[0].upper() == "DELETE":
            written.add(head[2].strip('"`'))

    engine = maker.kw["bind"]
    event.listen(engine, "before_cursor_execute", watch)
    try:
        run(maker, backfill=2)
        run(maker, recompute_all=True)
    finally:
        event.remove(engine, "before_cursor_execute", watch)
    assert written == {"period_signal_reports"}


def test_unreadable_stored_previous_period_counts_as_none(maker):
    seed_weeks(maker, W2)
    with maker() as session:
        repo = PeriodSignalRepo(session, comparable_from=COMPARABLE_FROM)
        repo.save_report({
            "period_kind": "week", "period_start": "2026-10-12", "period_end": "2026-10-18",
            "methodology_version": "m", "extraction_version": "e", "status": "ready",
            "thresholds": {}, "coverage": {}}, "h" * 64)
        assert repo.previous("week", W2) is None
