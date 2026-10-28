import json
from dataclasses import replace
from datetime import timedelta

from period_fixtures import (  # pylint: disable=import-error
    WEEK,
    fixture_period_input,
    synthetic,
)

from app.core.daily.signals_compute import METHODOLOGY_VERSION
from app.core.daily.signals_compute import payload_hash as daily_payload_hash
from app.core.daily.signals_model import DayCoverage
from app.core.periodic import signals_period
from app.core.periodic.period_compute import (
    PERIOD_METHODOLOGY_VERSION,
    compute_period,
    event_mix,
    new_this_period,
    payload_hash,
    top_stories,
)
from app.core.periodic.period_model import PeriodThresholds, PreviousPeriod


def day(n):
    return WEEK + timedelta(days=n)


def story(label, event, entities, publishers, *, articles=3, links=()):
    return {"label": label, "event_type": event, "entities": list(entities),
            "publishers": publishers, "articles": articles, "spikes": [],
            "links": [{"title": label, "url": f"https://{p}/{label}", "publisher": p}
                      for p in links]}


def snap(**fields):
    return {"status": "ready", "top_stories": [], "new": [], "event_counts": [], **fields}


# Coverage --------------------------------------------------------------------------------------
def test_coverage_line_counts_days_items_and_publishers():
    data = fixture_period_input()
    cov = compute_period(data)["coverage"]
    assert (cov["days"], cov["complete_days"], cov["missing_days"]) == (7, 7, [])
    assert cov["items"] == 397 and cov["extracted_share"] == 1.0
    assert cov["publishers"] == len({a.publisher for d in data.days for a in
                                     data.observations[d]})
    assert cov["quiet"] is False


def test_coverage_missing_day_is_listed_not_zero():
    data = fixture_period_input()
    coverage = {d: c for d, c in data.coverage.items() if d != day(2)}
    out = compute_period(replace(data, coverage=coverage))
    assert out["coverage"]["missing_days"] == [day(2).isoformat()]
    assert out["coverage"]["complete_days"] == 6
    assert out["coverage"]["items"] == 397 - len(data.observations[day(2)])
    assert out["status"] == "ready"


def test_coverage_incomplete_day_is_not_complete_and_quiet_flag():
    data = fixture_period_input()
    coverage = dict(data.coverage)
    coverage[day(0)] = DayCoverage(day(0), "signals", True, items=56, matched=56, extracted=10)
    assert compute_period(replace(data, coverage=coverage))["coverage"]["complete_days"] == 6
    quiet = synthetic({day(0): snap()}, items=10)
    assert compute_period(quiet)["quiet"] is True


def test_status_unavailable_partial_building_history_ready():
    data = fixture_period_input()
    assert compute_period(data)["status"] == "ready"
    assert compute_period(replace(data, previous=None))["status"] == "building_history"
    assert compute_period(synthetic({}))["status"] == "unavailable"
    few = {d: snap() for d in (day(0), day(1))}
    assert compute_period(synthetic(few, items=20))["status"] == "partial"


# Top stories -----------------------------------------------------------------------------------
def test_top_stories_merge_across_days_by_event_type_and_entities():
    data = synthetic({
        day(0): snap(top_stories=[story("GLM 5.3 launches", "model_release", ["GLM 5.3"], 2,
                                        links=["a.com", "b.com"])]),
        day(1): snap(top_stories=[story("Zhipu ships GLM 5.3", "model_release", ["GLM 5.3"], 4,
                                        links=["c.com", "d.com", "e.com"])]),
        day(2): snap(top_stories=[story("GLM 5.3 funding", "funding", ["GLM 5.3"], 2)]),
    })
    out = top_stories(data)
    assert [(s["event_type"], s["days"]) for s in out] == [
        ("model_release", [day(0).isoformat(), day(1).isoformat()]),
        ("funding", [day(2).isoformat()])]
    merged = out[0]
    assert merged["label"] == "Zhipu ships GLM 5.3" and merged["articles"] == 6
    assert merged["publishers"] == 5  # five distinct linked publishers beat the daily maximum 4
    assert len(merged["links"]) == 3


def test_top_stories_rank_by_publishers_then_days_and_cap():
    t = PeriodThresholds.for_kind("week")
    stories = {day(0): snap(top_stories=[story(f"s{i}", "funding", [f"E{i}"], 2 + (i % 3))
                                         for i in range(12)]),
               day(1): snap(top_stories=[story("s11", "funding", ["E11"], 2)])}
    out = top_stories(synthetic(stories))
    assert len(out) == t.top_max
    assert out[0]["publishers"] >= out[-1]["publishers"]
    same = [s for s in out if s["publishers"] == 4]
    assert [len(s["days"]) for s in same] == sorted((len(s["days"]) for s in same), reverse=True)


# New -------------------------------------------------------------------------------------------
def test_new_union_confirmed_first_with_first_seen_day():
    def item(name, level, entity_id, publishers=2):
        return {"entity_id": entity_id, "name": name, "level": level, "publishers": publishers}

    data = synthetic({
        day(0): snap(new=[item("Early A", "early", 1, 1), item("Conf B", "confirmed", 2)]),
        day(1): snap(new=[item("Early A", "confirmed", 1, 3), item("Early C", "early", 3, 1)]),
    })
    out = new_this_period(data)
    assert [(i["name"], i["level"], i["first_seen_day"]) for i in out] == [
        ("Early A", "confirmed", day(0).isoformat()),
        ("Conf B", "confirmed", day(0).isoformat()),
        ("Early C", "early", day(1).isoformat())]


def test_new_union_is_capped():
    items = [{"entity_id": i, "name": f"N{i:02}", "level": "early", "publishers": 1}
             for i in range(1, 30)]
    out = new_this_period(synthetic({day(0): snap(new=items)}))
    assert len(out) == PeriodThresholds.for_kind("week").new_period_max


# Top entities ----------------------------------------------------------------------------------
def test_top_entities_by_group_with_minimums():
    data = fixture_period_input()
    t = data.limits
    groups = compute_period(data)["top_entities"]
    assert set(groups) == {"models", "products", "companies", "technologies"}
    for name, items in groups.items():
        assert len(items) <= t.top_entity_max
        for item in items:
            assert item["articles"] >= t.top_entity_min_articles
            assert item["publishers"] >= t.top_entity_min_publishers
            assert item["days"] and item["links"]
        ranked = [(-i["articles"], -i["publishers"]) for i in items]
        assert ranked == sorted(ranked), name
    assert all(i["type"] == "model" for i in groups["models"])


# Rising and cooling ----------------------------------------------------------------------------
def test_rising_equals_the_sunday_snapshot():
    data = fixture_period_input()
    sunday = data.snapshots[data.end]
    out = compute_period(data)
    assert out["trend_source"] == "sunday_snapshot"
    assert out["rising"] == sunday["rising"] and out["rising"]
    assert out["cooling"] == sunday["cooling"]


def test_rising_from_the_helper_matches_the_sunday_snapshot_when_methodology_is_old():
    data = fixture_period_input()
    sunday = data.snapshots[data.end]
    old = {**sunday, "methodology_version": "daily-signals-0"}
    out = compute_period(replace(data, snapshots={**data.snapshots, data.end: old}))
    assert out["trend_source"] == "helper"
    keys = ("name", "type", "current_7d", "previous_7d", "expected_7d", "today", "publishers")
    assert [{k: i[k] for k in keys} for i in out["rising"]] == \
        [{k: i[k] for k in keys} for i in sunday["rising"]]
    assert [i["name"] for i in out["cooling"]] == [i["name"] for i in sunday["cooling"]]


def test_rising_snapshot_without_usable_windows_falls_back_to_the_helper():
    data = fixture_period_input()
    sunday = data.snapshots[data.end]
    spikes_only = {**sunday, "sections": {**sunday["sections"],
                                          "rising": {"state": "spikes_only", "note": None}}}
    out = compute_period(replace(data, snapshots={**data.snapshots, data.end: spikes_only}))
    assert out["trend_source"] == "helper"
    assert METHODOLOGY_VERSION == sunday["methodology_version"]


# Event mix -------------------------------------------------------------------------------------
def test_event_mix_sums_chips_with_delta_and_more():
    def chip(event, stories, articles=0):
        return {"event_type": event, "stories": stories, "articles": articles}

    data = synthetic({
        day(0): snap(event_counts=[chip("funding", 2, 5), chip("research", 3, 9)]),
        day(1): snap(event_counts=[chip("funding", 1, 2), chip("model_release", 2, 4)]),
    }, previous=PreviousPeriod("ready", 5, {"funding": 1, "model_release": 4}))
    mix = event_mix(data, compare=True)
    rows = {r["event_type"]: r for r in mix["types"]}
    assert (rows["funding"]["stories"], rows["funding"]["previous_stories"],
            rows["funding"]["delta"]) == (3, 1, 2)
    assert rows["model_release"]["delta"] == -2
    assert mix["more"] == {"types": 1, "stories": 3, "articles": 9}
    assert event_mix(data, compare=False)["types"][0]["delta"] is None


# Publisher breadth -----------------------------------------------------------------------------
def test_low_publisher_coverage_suppresses_the_comparison():
    data = fixture_period_input()
    publishers = compute_period(data)["coverage"]["publishers"]
    low = replace(data, previous=PreviousPeriod("ready", int(publishers / 0.6),
                                                {"funding": 1}))
    out = compute_period(low)
    assert out["comparison"]["state"] == "suppressed"
    assert out["comparison"]["reason"] == "low_publisher_coverage"
    assert out["rising"] == [] and out["cooling"] == []
    assert out["sections"]["rising"] == "hidden"
    assert all(r["delta"] is None for r in out["event_mix"]["types"])
    assert out["status"] == "ready"
    near = replace(data, previous=PreviousPeriod("ready", int(publishers / 0.75), {}))
    assert compute_period(near)["comparison"]["state"] == "ready"


def test_no_comparison_without_a_usable_previous_period():
    data = fixture_period_input()
    for previous in (None, PreviousPeriod("partial", 50, {}), PreviousPeriod("unavailable", 0, {})):
        out = compute_period(replace(data, previous=previous))
        assert out["comparison"]["state"] == "none"
        assert out["rising"] == []


# Hash and versions -----------------------------------------------------------------------------
def test_payload_hash_is_stable_and_ignores_day_order():
    data = fixture_period_input()
    first = compute_period(data)
    again = compute_period(fixture_period_input())
    assert payload_hash(first) == payload_hash(again)
    reordered = replace(
        data, snapshots=dict(reversed(list(data.snapshots.items()))),
        observations={d: list(reversed(a)) for d, a in reversed(list(data.observations.items()))},
        coverage=dict(reversed(list(data.coverage.items()))))
    assert payload_hash(compute_period(reordered)) == payload_hash(first)
    later = replace(data, generated_at=data.generated_at + timedelta(hours=3))
    assert payload_hash(compute_period(later)) == payload_hash(first)
    assert payload_hash is daily_payload_hash


def test_payload_is_json_and_records_versions_and_thresholds():
    out = compute_period(fixture_period_input())
    json.dumps(out)
    assert out["methodology_version"] == PERIOD_METHODOLOGY_VERSION
    assert out["daily_methodology_version"] == METHODOLOGY_VERSION
    assert out["thresholds"]["min_complete_days"] == 6
    assert (out["period_kind"], out["period_start"], out["period_end"]) == (
        "week", "2026-10-12", "2026-10-18")
    assert signals_period.compute_period is compute_period
