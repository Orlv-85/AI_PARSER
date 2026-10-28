"""Month rules of 017 R6: bounds, first month, status, risers, nightly default, brief."""
# run_periods starts the report with "brief": None; pylint infers only that literal.
# pylint: disable=unsubscriptable-object
import json
from dataclasses import replace
from datetime import date, datetime

import pytest
from period_brief_db import (  # pylint: disable=import-error
    Provider,
    good_answer,
    period_payload,
    store_digest,
)
from period_db import COMPARABLE_FROM, seed_day  # pylint: disable=import-error
from period_fixtures import fixture_period_input, synthetic  # pylint: disable=import-error
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.core.daily.signals_entities import Entity
from app.core.daily.signals_model import ArticleObs, DayCoverage, EntityMention
from app.core.periodic import period_run
from app.core.periodic.period_compute import compute_period, payload_hash
from app.core.periodic.period_model import (
    MONTH,
    WEEK,
    PeriodThresholds,
    PreviousPeriod,
    next_start,
    period_days,
)
from app.core.periodic.period_run import (
    PeriodRunError,
    PeriodRunOptions,
    brief_targets,
    first_month,
    latest_completed_month,
    run_periods,
    target_months,
)
from app.storage.daily_signals import DailySignalRepo
from app.storage.models_sql import Base, PeriodSignalBrief, PeriodSignalReport
from app.storage.period_signals import PeriodSignalRepo

NOV, DEC, OCT = date(2026, 11, 1), date(2026, 12, 1), date(2026, 10, 1)
FIRST_NIGHT = datetime(2026, 12, 1, 2, 30)


# Month totals ---------------------------------------------------------------------------------
def month_world(*, current, previous, publishers=4, prev_days=30, cur_days=30):
    """November (30 days) against October (31 days): `current` and `previous` map an entity name
    to its article count in that month. Every day is complete with 20 items."""
    entities, observations, coverage = {}, {}, {}
    next_id = [0]
    for start, counts, days in ((NOV, current, cur_days), (OCT, previous, prev_days)):
        for index, day in enumerate(period_days(MONTH, start)):
            if index >= days:
                continue
            coverage[day] = DayCoverage(day=day, kind="signals", published=True, items=20,
                                        matched=20, extracted=20)
            observations[day] = []
        for name, count in counts.items():
            key = f"model:{name.lower()}"
            entities[key] = Entity(
                entity_key=key, display_name=name, type_group="model", entity_type="model",
                vendor=None, vendor_class="", base_key=name.lower(), base_tokens=(),
                family_key=key, first_seen_day=OCT, needs_review=False)
            days = sorted(observations)
            days = [d for d in days if period_days(MONTH, start)[0] <= d <= period_days(
                MONTH, start)[-1]]
            for n in range(count):
                day = days[n % len(days)]
                next_id[0] += 1
                observations[day].append(ArticleObs(
                    article_id=next_id[0], scope_day=day, title=f"{name} {n}",
                    url=f"https://p{n % publishers}.example/{name}/{start}/{n}",
                    publisher=f"p{n % publishers}.example", published_at=None,
                    event_type="other",
                    mentions=(EntityMention(key, "model", name.lower(), "primary"),)))
    ids = {key: n for n, key in enumerate(sorted(entities), start=1)}
    return {"coverage": coverage, "observations": observations, "entities": entities,
            "entity_ids": ids}


READY = PreviousPeriod("ready", 4, {})


def month_input(world, *, previous=READY, start=NOV):
    snapshots = {d: {"status": "ready", "top_stories": [], "new": [], "event_counts": []}
                 for d in period_days(MONTH, start)}
    return synthetic(snapshots, kind=MONTH, start=start, previous=previous, **world)


def test_month_risers_and_coolers_compare_month_totals():
    world = month_world(current={"Alpha": 30, "Bravo": 2, "Charlie": 20},
                        previous={"Alpha": 5, "Bravo": 20, "Charlie": 20})
    out = compute_period(month_input(world))
    assert (out["status"], out["comparison"]["state"]) == ("ready", "ready")
    assert out["sections"]["rising"] == out["sections"]["cooling"] == "ready"
    assert out["trend_source"] == "month_helper"
    assert [(i["name"], i["current"], i["previous"]) for i in out["rising"]] == [("Alpha", 30, 5)]
    assert [(i["name"], i["current"], i["previous"]) for i in out["cooling"]] == [
        ("Bravo", 2, 20)]
    assert out["rising"][0]["expected"] == 5.0 and out["rising"][0]["links"]
    # 30 days against 31: the expectation is scaled by the extracted items of both months.
    assert out["thresholds"]["month_rising_min_current"] == 12


def test_month_risers_respect_the_month_minimums():
    t = PeriodThresholds.for_kind(MONTH)
    below = t.month_rising_min_current - 1
    world = month_world(current={"Alpha": below, "Bravo": 30},
                        previous={"Alpha": 0, "Bravo": 5}, publishers=t.month_rising_min_publishers)
    out = compute_period(month_input(world))
    assert [i["name"] for i in out["rising"]] == ["Bravo"]
    few = month_world(current={"Alpha": 30}, previous={"Alpha": 5},
                      publishers=t.month_rising_min_publishers - 1)
    assert compute_period(month_input(few))["rising"] == []


def test_month_risers_need_a_complete_previous_month():
    world = month_world(current={"Alpha": 30}, previous={"Alpha": 5}, prev_days=23)
    out = compute_period(month_input(world))
    assert out["comparison"]["state"] == "ready" and out["status"] == "ready"
    assert (out["sections"]["rising"], out["rising"], out["cooling"]) == (
        "unavailable", [], [])
    enough = month_world(current={"Alpha": 30}, previous={"Alpha": 5}, prev_days=24)
    assert compute_period(month_input(enough))["sections"]["rising"] == "ready"


def test_month_risers_need_the_previous_month_inside_the_comparable_range():
    world = month_world(current={"Alpha": 30}, previous={"Alpha": 5})
    data = replace(month_input(world), comparable_from=date(2026, 10, 10))
    assert compute_period(data)["sections"]["rising"] == "unavailable"


def test_no_comparison_without_a_usable_previous_month():
    world = month_world(current={"Alpha": 30}, previous={"Alpha": 5})
    for previous in (None, PreviousPeriod("partial", 4, {}), PreviousPeriod("unavailable", 0, {})):
        out = compute_period(month_input(world, previous=previous))
        assert out["status"] == "building_history"
        assert out["comparison"] == {"state": "none", "reason": "no_previous_period",
                                     "previous_publishers": None, "publisher_ratio": None}
        assert (out["sections"]["rising"], out["rising"], out["cooling"]) == ("hidden", [], [])
        assert all(row["delta"] is None for row in out["event_mix"]["types"])


def test_month_breadth_suppresses_the_comparison():
    world = month_world(current={"Alpha": 30}, previous={"Alpha": 5}, publishers=4)
    out = compute_period(month_input(world, previous=PreviousPeriod("ready", 100, {})))
    assert out["comparison"]["state"] == "suppressed"
    assert (out["status"], out["sections"]["rising"], out["rising"]) == ("ready", "hidden", [])


def test_month_event_mix_has_a_delta_against_the_previous_month():
    world = month_world(current={"Alpha": 3}, previous={"Alpha": 3})
    snapshots = {d: {"status": "ready", "top_stories": [], "new": [], "event_counts": [
        {"event_type": "funding", "stories": 1, "articles": 2}]} for d in period_days(MONTH, NOV)}
    data = synthetic(snapshots, kind=MONTH, start=NOV, **world,
                     previous=PreviousPeriod("ready", 4, {"funding": 25}))
    row = compute_period(data)["event_mix"]["types"][0]
    assert (row["event_type"], row["stories"], row["previous_stories"], row["delta"]) == (
        "funding", 30, 25, 5)


@pytest.mark.parametrize(("complete", "items", "previous", "status"), [
    (30, 600, True, "ready"), (24, 400, True, "ready"), (23, 600, True, "partial"),
    (30, 399, True, "partial"), (30, 600, False, "building_history"),
    (23, 600, False, "partial"), (0, 0, False, "unavailable")])
def test_month_status_thresholds(complete, items, previous, status):
    days = period_days(MONTH, NOV)[:complete]
    snapshots = {d: {"status": "ready"} for d in days}
    share = [items // complete + (1 if i < items % complete else 0) for i in range(complete)
             ] if complete else []
    coverage = {d: DayCoverage(day=d, kind="signals", published=True, items=n, matched=n,
                               extracted=n) for d, n in zip(days, share, strict=True)}
    data = synthetic(snapshots, kind=MONTH, start=NOV, coverage=coverage,
                     previous=PreviousPeriod("ready", 4, {}) if previous else None)
    out = compute_period(data)
    assert out["status"] == status
    assert out["quiet"] is (items < 600)


def test_a_week_payload_does_not_change_with_the_month_thresholds():
    week = compute_period(fixture_period_input())
    assert not [k for k in week["thresholds"] if k.startswith("month_")]
    assert len(week["thresholds"]) == 11
    # Pinned on origin/master before R6: the week fixture hash must not move.
    assert payload_hash(week) == (
        "84b0c0aae69e2e7695e4e48b7ec340311d1b0d10e2eb7e5cda4494bb5d8106b1")
    month = PeriodThresholds.for_kind(MONTH)
    assert month.month_rising_min_current == 12 and month.month_cooling_min_previous == 15
    assert PeriodThresholds.for_kind(WEEK).month_rising_max is None


# Bounds and targets ---------------------------------------------------------------------------
@pytest.mark.parametrize(("today", "latest", "length"), [
    (date(2026, 3, 1), date(2026, 2, 1), 28), (date(2028, 3, 1), date(2028, 2, 1), 29),
    (date(2026, 5, 1), date(2026, 4, 1), 30), (date(2026, 12, 1), date(2026, 11, 1), 30),
    (date(2027, 1, 1), date(2026, 12, 1), 31), (date(2026, 12, 31), date(2026, 11, 1), 30)])
def test_latest_completed_month_is_the_one_before_the_current(today, latest, length):
    assert latest_completed_month(today) == latest
    assert len(period_days(MONTH, latest)) == length


def test_the_first_month_is_the_first_full_month_in_the_comparable_range():
    assert first_month(date(2026, 10, 10)) == NOV  # October is partial
    assert first_month(date(2026, 10, 1)) == OCT  # a first day counts
    assert first_month(date(2026, 12, 31)) == date(2027, 1, 1)  # year change
    assert next_start(MONTH, DEC) == date(2027, 1, 1)


def targets(**options):
    today = options.pop("today")
    return target_months(PeriodRunOptions(kind=MONTH, **options), today=today,
                         comparable_from=COMPARABLE_FROM)


def test_the_nightly_default_does_nothing_before_the_first_month_is_complete():
    for today in (date(2026, 10, 28), date(2026, 11, 15), date(2026, 11, 30)):
        wanted, early = targets(today=today)
        assert wanted == [] and all(e < NOV for e in early)
    assert targets(today=date(2026, 12, 1)) == ([NOV], [])
    assert targets(today=date(2026, 12, 31)) == ([NOV], [])
    assert targets(today=date(2027, 1, 1)) == ([DEC], [])


def test_backfill_recompute_all_and_period_of_months():
    today = date(2027, 1, 1)
    assert targets(today=today, backfill=3) == ([NOV, DEC], [OCT])
    assert targets(today=today, recompute_all=True) == ([NOV, DEC], [])
    assert targets(today=today, period=date(2026, 11, 17)) == ([NOV], [])
    assert targets(today=date(2026, 10, 28), recompute_all=True) == ([], [])


@pytest.mark.parametrize("period", [date(2026, 10, 15), date(2026, 12, 1), date(2027, 1, 1)])
def test_october_and_uncompleted_months_are_refused(period):
    with pytest.raises(PeriodRunError):
        targets(today=date(2026, 12, 15), period=period)


def test_month_brief_targets_are_the_latest_completed_month_when_computed():
    options = PeriodRunOptions(kind=MONTH)
    assert brief_targets(options, [NOV], today=date(2026, 12, 1)) == [NOV]
    assert not brief_targets(options, [NOV], today=date(2027, 1, 1))
    assert brief_targets(replace(options, with_brief=True), [NOV], today=date(2027, 1, 1)) == [NOV]


# Run on a database ----------------------------------------------------------------------------
@pytest.fixture(name="maker")
def maker_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'month.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


def settings(**kwargs):
    return Settings(_env_file=None, daily_signals_comparable_from=COMPARABLE_FROM,
                    period_signals_enabled=True, **kwargs)


def seed_month(maker, start):
    days = period_days(MONTH, start)
    names = tuple(f"Model{n}" for n in range(14))
    for day in days:
        seed_day(maker, day, names=names)
    with maker() as session:
        DailySignalRepo(session, comparable_from=COMPARABLE_FROM).recompute_reports(
            days[-1], now=FIRST_NIGHT)
        session.commit()


def test_a_database_run_stores_november_then_compares_december(maker):
    seed_month(maker, NOV)
    seed_month(maker, DEC)
    with maker() as session:
        first = run_periods(session, settings(), PeriodRunOptions(kind=MONTH),
                            now=FIRST_NIGHT)
    assert (first["written"], first["skipped_before_first"]) == (["2026-11-01"], [])
    assert first["periods"]["2026-11-01"] == {"end": "2026-11-30", "status": "building_history",
                                               "written": True}
    with maker() as session:
        again = run_periods(session, settings(), PeriodRunOptions(kind=MONTH), now=FIRST_NIGHT)
        assert (again["written"], again["unchanged"]) == ([], 1)
        late = run_periods(session, settings(), PeriodRunOptions(kind=MONTH, backfill=3),
                           now=datetime(2027, 1, 1, 2, 30))
    assert late["written"] == ["2026-12-01"]
    assert late["skipped_before_first"] == ["2026-10-01"]
    assert late["periods"]["2026-11-01"]["written"] is False
    with maker() as session:
        repo = PeriodSignalRepo(session, comparable_from=COMPARABLE_FROM)
        november, december = repo.get_report("month", NOV), repo.get_report("month", DEC)
        assert (november.period_end, december.period_end) == (date(2026, 11, 30),
                                                                date(2026, 12, 31))
        payload = json.loads(december.payload)
        assert december.status == "ready" and payload["comparison"]["state"] == "ready"
        assert payload["coverage"]["days"] == 31 and payload["sections"]["rising"] == "ready"
        assert json.loads(november.payload)["sections"]["rising"] == "hidden"
        assert repo.latest("month").period_start == DEC
        assert session.scalar(select(PeriodSignalReport).where(
            PeriodSignalReport.period_start == OCT)) is None


def test_the_nightly_default_before_december_writes_nothing(maker):
    seed_month(maker, NOV)
    for now in (datetime(2026, 10, 28, 3, 0), datetime(2026, 11, 30, 3, 0)):
        with maker() as session:
            report = run_periods(session, settings(), PeriodRunOptions(kind=MONTH), now=now)
        assert report["state"] == "ok" and not report["written"] and not report["periods"]
    with maker() as session:
        assert session.scalar(select(PeriodSignalReport)) is None


# Month brief ----------------------------------------------------------------------------------
def brief_settings():
    return settings(period_signals_brief_enabled=True)


def brief_run(maker, tmp_path, provider, now, **options):
    with maker() as session:
        return run_periods(session, brief_settings(), PeriodRunOptions(
            kind=MONTH, cache_dir=tmp_path / "cache", **options), now=now,
            transport=provider.transport)


def test_the_month_brief_is_attempted_only_on_a_month_row(maker, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_API_KEY", "secret-key")
    monkeypatch.setattr(period_run, "compute_period", lambda data: period_payload(
        data.kind, data.start, status="building_history"))
    store_digest(maker, period_payload("month", NOV))
    provider = Provider(lambda request: good_answer(request, sentences=5))
    before = brief_run(maker, tmp_path, provider, datetime(2026, 11, 30, 3, 0))
    assert not before["written"] and not before["brief"]["periods"]
    assert not provider.requests
    first = brief_run(maker, tmp_path, provider, FIRST_NIGHT)
    assert first["brief"]["periods"] == {"month:2026-11-01": "ok"}
    body = provider.requests[0]
    assert body["max_tokens"] == 1500 and len(provider.requests) == 1
    again = brief_run(maker, tmp_path, provider, datetime(2026, 12, 2, 3, 0))
    assert again["brief"]["periods"] == {"month:2026-11-01": "cached"}
    assert len(provider.requests) == 1
    with maker() as session:
        row = session.scalar(select(PeriodSignalBrief))
        assert (row.period_kind, row.period_start, row.status) == ("month", NOV, "ok")


def test_a_partial_month_gets_no_brief(maker, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_API_KEY", "secret-key")
    monkeypatch.setattr(period_run, "compute_period", lambda data: period_payload(
        data.kind, data.start, status="partial"))
    store_digest(maker, period_payload("month", NOV))
    provider = Provider()
    report = brief_run(maker, tmp_path, provider, FIRST_NIGHT)
    assert report["brief"]["periods"] == {"month:2026-11-01": "skipped:status_partial"}
    assert not provider.requests
