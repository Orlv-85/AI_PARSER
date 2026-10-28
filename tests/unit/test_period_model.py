from datetime import date

import pytest

from app.core.periodic.period_model import (
    MONTH,
    WEEK,
    PeriodThresholds,
    period_bounds,
    period_days,
    period_status,
    previous_start,
    week_start,
)


def test_week_runs_monday_to_sunday():
    for day in (date(2026, 10, 12), date(2026, 10, 15), date(2026, 10, 18)):
        assert period_bounds(WEEK, day) == (date(2026, 10, 12), date(2026, 10, 18))
    assert week_start(date(2026, 10, 12)).weekday() == 0
    assert period_bounds(WEEK, date(2026, 10, 18))[1].weekday() == 6
    assert len(period_days(WEEK, date(2026, 10, 14))) == 7


def test_week_across_a_year_change():
    assert period_bounds(WEEK, date(2027, 1, 1)) == (date(2026, 12, 28), date(2027, 1, 3))
    assert previous_start(WEEK, date(2027, 1, 4)) == date(2026, 12, 28)


@pytest.mark.parametrize(("day", "length"), [
    (date(2026, 2, 10), 28), (date(2028, 2, 10), 29), (date(2026, 4, 30), 30),
    (date(2026, 12, 31), 31)])
def test_month_lengths(day, length):
    start, end = period_bounds(MONTH, day)
    assert (start.day, end.day) == (1, length)
    assert len(period_days(MONTH, day)) == length


def test_previous_month_crosses_the_year():
    assert previous_start(MONTH, date(2027, 1, 1)) == date(2026, 12, 1)
    assert previous_start(MONTH, date(2026, 3, 1)) == date(2026, 2, 1)


def test_thresholds_by_kind():
    week, month = PeriodThresholds.for_kind(WEEK), PeriodThresholds.for_kind(MONTH)
    assert (week.min_complete_days, week.min_items, week.quiet_items) == (6, 100, 150)
    assert (month.min_complete_days, month.min_items, month.quiet_items) == (24, 400, 600)
    assert week.breadth_ratio == month.breadth_ratio == 0.7
    with pytest.raises(ValueError):
        PeriodThresholds.for_kind("year")


def test_period_status_precedence():
    t = PeriodThresholds.for_kind(WEEK)

    def status(snapshot_days=7, complete_days=7, items=300, previous_ready=True):
        return period_status(t, snapshot_days=snapshot_days, complete_days=complete_days,
                             items=items, previous_ready=previous_ready)

    assert status() == "ready"
    assert status(previous_ready=False) == "building_history"
    assert status(complete_days=5, previous_ready=False) == "partial"
    assert status(items=99, previous_ready=False) == "partial"
    assert status(snapshot_days=0, complete_days=0, items=0, previous_ready=False) == "unavailable"
    assert status(snapshot_days=0) == "unavailable"


def test_a_missing_day_is_not_zero():
    t = PeriodThresholds.for_kind(WEEK)
    # 6 of 7 days complete: one missing day does not make the week partial.
    assert period_status(t, snapshot_days=6, complete_days=6, items=300,
                         previous_ready=True) == "ready"
    assert period_status(t, snapshot_days=5, complete_days=5, items=300,
                         previous_ready=True) == "partial"
