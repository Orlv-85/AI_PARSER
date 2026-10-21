from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.core.weekly.analytics import Coverage, Observation, calculate, windows

REPORT_DATE = date(2026, 10, 4)
NOW = datetime(2026, 10, 5, tzinfo=UTC)
TOPICS = [{"id": "coding", "label": "Coding agents"}, {"id": "background", "label": "Other AI"}]


def fixture_counts(counts: list[int], volumes: list[int] | None = None,
                   publishers: int = 5) -> tuple[list[Observation], list[Coverage]]:
    volumes = volumes or [100] * 5
    observations = []
    coverage = []
    for week, (start, _) in enumerate(windows(REPORT_DATE)):
        for publisher in range(publishers):
            name = f"publisher-{publisher}"
            for event in range(volumes[week]):
                topic_id = "coding" if event < counts[week] else "background"
                observations.append(Observation(
                    id=f"{week}-{publisher}-{event}", event_id=f"{week}-{event}", publisher=name,
                    published_at=start + timedelta(days=event % 7, hours=12), topic_id=topic_id,
                    title="Coding agents" if topic_id == "coding" else "Other AI news",
                    url=f"https://example.com/{week}/{publisher}/{event}",
                    excerpt="Observed news evidence.",
                ))
            for day in range(7):
                coverage.append(Coverage(name, (start + timedelta(days=day)).date(),
                                         1, 1, date(2026, 1, 1)))
    return observations, coverage


def report(counts: list[int], volumes: list[int] | None = None) -> dict:
    observations, coverage = fixture_counts(counts, volumes)
    return dict(calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW))


def topic(result: dict) -> dict:
    return next(item for section in ("new", "trending_up", "trending_down", "other_signals")
                for item in result[section] if item["topic_id"] == "coding")


@pytest.mark.parametrize(("counts", "state", "delta", "growth"), [
    ([12, 5, 5, 5, 5], "up", 7, 140),
    ([5, 12, 12, 12, 12], "down", -7, -100 * 7 / 12),
    ([0, 8, 8, 8, 8], "down", -8, -100),
    ([5, 5, 5, 5, 5], "stable", 0, 0),
    ([2, 1, 1, 1, 1], "stable", 1, 100),
    ([5, 0, 0, 0, 0], "new", 5, None),
    ([5, 0, 5, 0, 0], "resurfacing", 5, None),
])
def test_attention_rules(counts, state, delta, growth) -> None:
    result = report(counts)
    item = topic(result)
    assert result["status"] == "ready"
    assert item["state"] == state
    assert item["delta_pp"] == pytest.approx(delta)
    assert item["growth_pct"] == pytest.approx(growth) if growth is not None else (
        item["growth_pct"] is None)


def test_volume_doubling_with_same_share_is_stable() -> None:
    result = report([10, 5, 5, 5, 5], [200, 100, 100, 100, 100])
    assert topic(result)["event_count_current"] == 10
    assert topic(result)["state"] == "stable"
    assert topic(result)["delta_pp"] == 0


def test_failed_current_coverage_cannot_be_down() -> None:
    observations, coverage = fixture_counts([0, 8, 8, 8, 8])
    start = windows(REPORT_DATE)[0][0].date()
    coverage = [replace(c, successful=0) if c.day >= start and c.publisher == "publisher-0"
                else c for c in coverage]
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert result["status"] == "insufficient_data"
    assert not result["trending_down"]
    assert topic(result)["state"] == "insufficient_evidence"


@pytest.mark.parametrize("quality", ["unknown", "truncated", "low_volume", "unresolved"])
def test_quality_failures_suppress_confirmation(quality: str) -> None:
    observations, coverage = fixture_counts([12, 5, 5, 5, 5])
    reason = {"unknown": "coverage_unknown", "truncated": "coverage_unknown",
              "low_volume": "low_volume", "unresolved": "classification_incomplete"}[quality]
    if quality == "unknown":
        coverage = []
    elif quality == "truncated":
        coverage = [replace(c, complete=False) for c in coverage]
    elif quality == "low_volume":
        observations = observations[:30]
        reason = "source_outage"
    else:
        observations = [replace(r, topic_id=None) for r in observations]
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert not result["trending_up"]
    assert result["quality"]["reason"] == reason


def test_unknown_history_blocks_new_but_not_two_week_growth() -> None:
    observations, coverage = fixture_counts([5, 0, 0, 0, 0])
    start = windows(REPORT_DATE)[1][0].date()
    coverage = [c for c in coverage if c.day >= start]
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert result["status"] == "ready"
    assert not result["new"]
    assert topic(result)["reason"] == "insufficient_history"
    assert result["section_status"]["new"]["reason"] == "insufficient_history"


def test_duplicates_within_event_publisher_week_do_not_add_support() -> None:
    observations, coverage = fixture_counts([5, 0, 0, 0, 0])
    current = windows(REPORT_DATE)[0][0]
    observations = [replace(r, event_id="one-launch")
                    if r.topic_id == "coding" and r.published_at >= current else r
                    for r in observations]
    observations += [replace(r, id=f"copy-{i}-{r.id}") for i in range(20)
                     for r in observations[:10]]
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert topic(result)["event_count_current"] == 1
    assert topic(result)["state"] == "insufficient_evidence"


def test_twenty_publisher_syndication_remains_one_event() -> None:
    observations, coverage = fixture_counts([1, 0, 0, 0, 0], publishers=20)
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert topic(result)["event_count_current"] == 1
    assert topic(result)["publisher_count_current"] == 20
    assert not result["new"]


def test_new_publisher_excluded_symmetrically() -> None:
    observations, coverage = fixture_counts([5, 5, 5, 5, 5], publishers=6)
    start = windows(REPORT_DATE)[0][0].date()
    coverage = [replace(c, configured_at=start) if c.publisher == "publisher-5" else c
                for c in coverage]
    observations = [replace(r, topic_id="coding") if r.publisher == "publisher-5" else r
                    for r in observations]
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert result["quality"]["cohort_size"] == 5
    assert topic(result)["state"] == "stable"


def test_equal_publisher_weighting_and_unresolved_denominators() -> None:
    observations, coverage = fixture_counts([5, 5, 5, 5, 5])
    start, _ = windows(REPORT_DATE)[0]
    # Additional prolific-source observations are unresolved but stay in denominator.
    observations += [Observation(f"extra-{i}", f"extra-{i}", "publisher-0",
                                 start + timedelta(days=i % 7), None) for i in range(50)]
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert topic(result)["share_current"] == pytest.approx((5 / 150 + 4 * 5 / 100) / 5)
    assert result["quality"]["weeks"][0]["observations"] == 550
    assert result["quality"]["reason"] == "classification_incomplete"


def test_multilingual_titles_do_not_change_identity_or_metrics() -> None:
    observations, coverage = fixture_counts([5, 5, 5, 5, 5])
    start = windows(REPORT_DATE)[0][0]
    changed = [replace(r, title="Агенты программирования") if r.published_at >= start else r
               for r in observations]
    result = calculate(REPORT_DATE, changed, coverage, TOPICS, now=NOW)
    assert topic(result)["state"] == "stable"
    assert topic(result)["topic_id"] == "coding"


def test_historical_match_outside_cohort_disqualifies_new() -> None:
    observations, coverage = fixture_counts([5, 0, 0, 0, 0])
    observations.append(Observation("outside", "old-event", "outside-cohort",
                                    windows(REPORT_DATE)[3][0], "coding"))
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert topic(result)["state"] == "resurfacing"


def test_ambiguous_history_prevents_confirmation() -> None:
    observations, coverage = fixture_counts([5, 0, 0, 0, 0])
    observations.append(Observation("ambiguous", "old", "outside-cohort",
                                    windows(REPORT_DATE)[3][0], None,
                                    possible_topics=("coding",)))
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert not result["new"]
    assert topic(result)["reason"] == "classification_incomplete"


def test_publication_days_are_utc_not_source_local_days() -> None:
    row = Observation("offset", "offset", "publisher", datetime(
        2026, 10, 4, 0, 30, tzinfo=timezone(timedelta(hours=3))), "coding")
    assert row.published_at == datetime(2026, 10, 3, 21, 30, tzinfo=UTC)
    with pytest.raises(ValueError, match="timezone"):
        Observation("naive", "naive", "publisher", datetime(2026, 10, 4), "coding")


def test_exact_window_boundaries_and_provisional_week() -> None:
    periods = windows(REPORT_DATE)
    assert periods[0][0] == datetime(2026, 9, 28, tzinfo=UTC)
    assert periods[-1][0] == datetime(2026, 8, 31, tzinfo=UTC)
    observations, coverage = fixture_counts([12, 5, 5, 5, 5])
    observations += [Observation("at-end", "at-end", "publisher-0", periods[0][1], "coding"),
                     Observation("at-start", "at-start", "publisher-0", periods[-1][0], "coding")]
    result = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    assert topic(result)["event_count_current"] == 12
    assert result["quality"]["counted_observations"] == 2501
    provisional = calculate(REPORT_DATE, observations, coverage, TOPICS,
                            now=periods[0][1] - timedelta(microseconds=1))
    assert provisional["status"] == "provisional"
    assert not provisional["trending_up"]
    assert provisional["section_status"]["trending_up"]["reason"] == "partial_window"


def test_replay_ordering_evidence_and_complete_input_over_two_hundred() -> None:
    observations, coverage = fixture_counts([12, 5, 5, 5, 5])
    first = calculate(REPORT_DATE, observations, coverage, TOPICS, now=NOW)
    second = calculate(REPORT_DATE, list(reversed(observations)), coverage, TOPICS, now=NOW)
    assert first == second
    assert first["quality"]["input_count"] == 2500
    assert topic(first)["event_count_current"] == 12
    assert {e["window"] for e in topic(first)["evidence"]} == {"current", "previous"}


def test_ready_empty_sections_explain_thresholds() -> None:
    result = report([5, 5, 5, 5, 5])
    assert not result["trending_up"]
    assert result["section_status"]["trending_up"]["reason"] == "no_qualifying_topics"
    assert result["section_status"]["trending_down"]["message"] == (
        "No topics met the decline threshold this week.")
