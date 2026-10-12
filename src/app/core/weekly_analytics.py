"""Deterministic attention metrics. No storage or provider calls."""
# pylint: disable=too-many-instance-attributes,too-many-branches,too-many-statements

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

METHODOLOGY_VERSION = "attention-v2.1"
SECTION_STATES = {"new": "new", "trending_up": "up", "trending_down": "down"}
EMPTY_MESSAGES = {
    "coverage_unknown": "Insufficient comparable source coverage.",
    "source_outage": "Insufficient comparable source coverage.",
    "low_volume": "Insufficient comparable source coverage.",
    "classification_incomplete": "Topic classification is incomplete.",
    "input_incomplete": "Insufficient comparable source coverage.",
    "insufficient_history": "Collecting history to verify new topics.",
    "partial_window": "This week is still in progress.",
}


@dataclass(frozen=True)
class Thresholds:
    min_publishers: int = 5
    retention: float = 0.8
    success_rate: float = 0.9
    successful_days: int = 6
    min_observations: int = 100
    assignment_rate: float = 0.9
    assignment_difference: float = 0.05
    support_events: int = 5
    support_publishers: int = 3
    support_days: int = 2
    growth: float = 0.3
    delta_pp: float = 1.0
    event_delta: int = 3


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class Observation:
    id: str
    event_id: str
    publisher: str
    published_at: datetime | None
    topic_id: str | None
    title: str = ""
    url: str = ""
    excerpt: str = ""
    article_id: int | None = None
    eligible: bool = True
    possible_topics: tuple[str, ...] = ()
    calendar_date: str | None = None
    publication_precision: str | None = None
    publication_interval: dict | None = None

    def __post_init__(self) -> None:
        if self.published_at is None:
            if not self.publication_interval:
                raise ValueError("Calendar observation requires a UTC uncertainty interval")
            low, high = (datetime.fromisoformat(self.publication_interval[k])
                         for k in ("start", "end"))
            if low.tzinfo is None or high.tzinfo is None or low >= high:
                raise ValueError("Calendar interval requires ordered timezone-aware bounds")
            return
        if self.published_at.tzinfo is None:
            raise ValueError("Observation publication time requires a timezone")
        object.__setattr__(self, "published_at", self.published_at.astimezone(UTC))


def in_window(row: Observation, start: datetime, end: datetime) -> bool:
    if row.published_at is not None:
        return start <= row.published_at < end
    interval = row.publication_interval or {}
    return (start <= datetime.fromisoformat(interval["start"])
            and datetime.fromisoformat(interval["end"]) <= end)


def order_time(row: Observation) -> datetime:
    return row.published_at or datetime.fromisoformat((row.publication_interval or {})["start"])


@dataclass(frozen=True)
class Coverage:
    publisher: str
    day: date
    expected: int
    successful: int
    configured_at: date
    complete: bool = True
    daily: bool = True


def windows(report_date: date) -> list[tuple[datetime, datetime]]:
    end = datetime.combine(report_date + timedelta(days=1), time.min, UTC)
    return [(end - timedelta(days=7 * (i + 1)), end - timedelta(days=7 * i))
            for i in range(5)]


def empty_section(section: str, reason: str) -> dict[str, str]:
    defaults = {
        "new": "No confirmed new topics in the observed 28-day history.",
        "trending_up": "No topics met the growth threshold this week.",
        "trending_down": "No topics met the decline threshold this week.",
    }
    return {"reason": reason, "message": EMPTY_MESSAGES.get(reason, defaults[section])}


def _health(coverage: list[Coverage], periods: list[tuple[datetime, datetime]],
            thresholds: Thresholds) -> list[set[str]]:
    healthy: list[set[str]] = []
    baseline_start = periods[1][0].date()
    for start, end in periods:
        groups: dict[str, list[Coverage]] = defaultdict(list)
        for row in coverage:
            if (start.date() <= row.day < end.date() and row.daily
                    and row.configured_at < baseline_start):
                groups[row.publisher].append(row)
        healthy.append({publisher for publisher, rows in groups.items()
                        if all(row.complete for row in rows)
                        and len({row.day for row in rows}) == 7
                        and sum(row.expected for row in rows) > 0
                        and sum(row.successful for row in rows) / sum(
                            row.expected for row in rows) >= thresholds.success_rate
                        and len({row.day for row in rows if row.successful > 0})
                        >= thresholds.successful_days})
    return healthy


def _quality(rows: list[list[Observation]], cohort: set[str], thresholds: Thresholds,
             indices: range) -> tuple[str | None, list[dict[str, Any]]]:
    stats = []
    for i in indices:
        selected = [row for row in rows[i] if row.publisher in cohort]
        resolved = sum(row.topic_id is not None for row in selected)
        stats.append({"window": i, "observations": len(selected), "resolved": resolved,
                      "unresolved": len(selected) - resolved,
                      "unresolved_share": 1 - resolved / len(selected) if selected else 0,
                      "assignment_rate": resolved / len(selected) if selected else 0})
    if any(row["observations"] < thresholds.min_observations for row in stats):
        return "low_volume", stats
    rates = [row["assignment_rate"] for row in stats]
    if min(rates) < thresholds.assignment_rate or (
        max(rates) - min(rates) > thresholds.assignment_difference + 1e-12
    ):
        return "classification_incomplete", stats
    return None, stats


def _metrics(rows: list[Observation], topic_id: str, cohort: set[str]) -> dict[str, Any]:
    denominators: dict[str, int] = defaultdict(int)
    numerators: dict[str, int] = defaultdict(int)
    selected = []
    for row in rows:
        if row.publisher not in cohort:
            continue
        denominators[row.publisher] += 1
        if row.topic_id == topic_id:
            numerators[row.publisher] += 1
            selected.append(row)
    share = sum(numerators[p] / denominators[p] for p in sorted(cohort)
                if denominators[p]) / len(cohort) if cohort else 0.0
    return {"share": share, "events": len({r.event_id for r in selected}),
            "publishers": len({r.publisher for r in selected}),
            "days": len({r.published_at.date() for r in selected if r.published_at is not None}),
            "rows": selected}


def _supported(metrics: dict[str, Any], thresholds: Thresholds) -> bool:
    return bool(metrics["events"] >= thresholds.support_events
            and metrics["publishers"] >= thresholds.support_publishers
                and metrics["days"] >= thresholds.support_days)


def _evidence(rows: list[Observation], periods: list[tuple[datetime, datetime]]) -> list[dict]:
    selected = []
    events: set[str] = set()
    publishers: set[str] = set()
    # Alternate weeks; Down naturally selects the prior side when W0 is empty.
    ordered = sorted(rows, key=lambda r: (order_time(r), r.id), reverse=True)
    sides = [[r for r in ordered if in_window(r, start, end)]
             for start, end in periods[:2]]
    previous_seed = next((r for r in sides[1]
                          if not sides[0] or r.publisher != sides[0][0].publisher), None)
    seed = sides[0][:1] + ([previous_seed] if previous_seed else [])
    alternated = seed + [r for pair in zip(sides[0], sides[1], strict=False) for r in pair]
    for row in alternated + ordered:
        if (row.event_id in events or row.publisher in publishers
                or not row.url.startswith(("https://", "http://"))):
            continue
        events.add(row.event_id)
        publishers.add(row.publisher)
        selected.append({"id": row.id, "article_id": row.article_id,
                         "event_id": row.event_id, "title": row.title, "url": row.url,
                         "publisher": row.publisher, "published_at": (
                             row.published_at.isoformat() if row.published_at else None),
                         "calendar_date": row.calendar_date,
                         "publication_precision": row.publication_precision,
                         "publication_interval": row.publication_interval,
                         "window": "current" if row in sides[0] else "previous",
                         "excerpt": row.excerpt[:2000]})
        if len(selected) == 6:
            break
    return selected


def calculate(report_date: date, observations: list[Observation], coverage: list[Coverage],
              topics: list[dict], *, now: datetime, input_complete: bool = True,
              history_complete: bool = True,
              thresholds: Thresholds = DEFAULT_THRESHOLDS) -> dict[str, Any]:
    periods = windows(report_date)
    unique: dict[tuple[str, str, int], Observation] = {}
    for row in sorted(observations, key=lambda r: r.id):
        if not row.eligible:
            continue
        for i, (start, end) in enumerate(periods):
            if in_window(row, start, end):
                unique.setdefault((row.event_id, row.publisher, i), row)
                break
    rows = [[r for (_, _, w), r in unique.items() if w == i] for i in range(5)]
    healthy = _health(coverage, periods, thresholds)
    cohort = healthy[0] & healthy[1]
    # An empty healthy publisher cannot contribute a proportion on either side.
    cohort &= {r.publisher for r in rows[0]} & {r.publisher for r in rows[1]}
    reason, stats = _quality(rows, cohort, thresholds, range(2))
    if not coverage:
        reason = "coverage_unknown"
    elif (len(cohort) < thresholds.min_publishers or not healthy[1]
          or len(cohort) / len(healthy[1]) < thresholds.retention):
        reason = "source_outage" if healthy[1] else "coverage_unknown"
    coverage_reason = reason if reason in {"coverage_unknown", "source_outage"} else None
    if not input_complete:
        reason = "input_incomplete"
    if now < periods[0][1]:
        reason = "partial_window"
    novelty = set.intersection(*healthy) & cohort
    for week in rows:
        novelty &= {r.publisher for r in week}
    novelty_reason, novelty_stats = _quality(rows, novelty, thresholds, range(5))
    history_ready = (history_complete and not novelty_reason
                     and len(novelty) >= thresholds.min_publishers
                     and bool(cohort) and len(novelty) / len(cohort) >= thresholds.retention)
    result: dict[str, Any] = {
        "report_date": report_date.isoformat(), "date_from": periods[0][0].date().isoformat(),
        "date_to": report_date.isoformat(), "methodology_version": METHODOLOGY_VERSION,
        "status": "provisional" if reason == "partial_window" else (
            "insufficient_data" if reason else "ready"), "narrative_mode": "template",
        "quality": {"reason": reason, "cohort": sorted(cohort), "cohort_size": len(cohort),
                    "coverage_reason": coverage_reason, "input_complete": input_complete,
                    "topic_count_scope": "observed" if reason else "comparable_cohort",
                    "normalized_metrics_available": bool(cohort),
                    "weeks": stats, "novelty_cohort": sorted(novelty),
                    "novelty_weeks": novelty_stats, "history_ready": history_ready,
                    "input_count": len(observations), "counted_observations": len(unique),
                    "observed_weeks": [{"window": i, "observations": len(week),
                                        "unresolved": sum(r.topic_id is None for r in week)}
                                       for i, week in enumerate(rows)],
                    "excluded_ineligible": sum(not r.eligible for r in observations),
                    "excluded_publishers": sorted({r.publisher for r in observations} - cohort),
                    "excluded_publisher_observations": [sum(r.publisher not in cohort for r in week)
                                                        for week in rows],
                    "thresholds": asdict(thresholds)},
        "new": [], "trending_up": [], "trending_down": [], "other_signals": [],
    }
    for topic in topics:
        topic_id = topic["id"]
        current, previous = [_metrics(rows[i], topic_id, cohort) for i in range(2)]
        observed_current, observed_previous = [
            _metrics(rows[i], topic_id, {r.publisher for r in rows[i]}) for i in range(2)]
        historical = [r for week in rows[1:] for r in week if r.topic_id == topic_id]
        ambiguous_history = any(r.topic_id is None and (not r.possible_topics
                                or topic_id in r.possible_topics) for week in rows[1:]
                                for r in week)
        delta = 100 * (current["share"] - previous["share"])
        growth = ((current["share"] - previous["share"]) / previous["share"]
                  if previous["share"] else None)
        state = "insufficient_evidence" if reason else "stable"
        topic_reason = reason
        if not reason:
            if previous["share"] == 0 and current["events"]:
                if not _supported(current, thresholds):
                    state = "insufficient_evidence"
                elif historical:
                    state = "resurfacing"
                elif (history_ready and not ambiguous_history and
                      _supported(_metrics(rows[0], topic_id, novelty), thresholds)):
                    state = "new"
                    current = _metrics(rows[0], topic_id, novelty)
                    delta = 100 * current["share"]
                else:
                    state = "insufficient_evidence"
                    topic_reason = (
                        "classification_incomplete" if history_ready and ambiguous_history
                        else "insufficient_history")
            elif growth is not None:
                if (_supported(current, thresholds) and growth >= thresholds.growth
                        and delta >= thresholds.delta_pp
                        and current["events"] - previous["events"] >= thresholds.event_delta):
                    state = "up"
                elif (_supported(previous, thresholds) and growth <= -thresholds.growth
                      and delta <= -thresholds.delta_pp
                      and previous["events"] - current["events"] >= thresholds.event_delta):
                    state = "down"
        facts_current, facts_previous = ((observed_current, observed_previous) if reason else
                                        (current, previous))
        evidence = _evidence(facts_current["rows"] + facts_previous["rows"], periods)
        first = min((r.published_at.isoformat() for r in observations
                     if r.topic_id == topic_id and r.published_at is not None), default=None)
        if any(r.topic_id == topic_id and r.published_at is None for r in observations):
            first = None
        item = {"topic_id": topic_id, "title": topic["label"], "state": state,
                "reason": topic_reason, "event_count_current": facts_current["events"],
                "event_count_previous": facts_previous["events"],
                "publisher_count_current": facts_current["publishers"],
                "publisher_count_previous": facts_previous["publishers"],
                "observed_event_count_current": observed_current["events"],
                "observed_event_count_previous": observed_previous["events"],
                "share_current": current["share"] if cohort else None,
                "share_previous": previous["share"] if cohort else None,
                "delta_pp": delta if cohort else None,
                "growth_pct": 100 * growth if growth is not None and cohort else None,
                "first_observed_at": first, "evidence": evidence,
                "url": evidence[0]["url"] if evidence else "",
                "summary": ((f"Observed event groups: {facts_previous['events']} to "
                             f"{facts_current['events']}. Trend confirmation is unavailable; "
                             "growth, decline and novelty are unconfirmed.") if reason else
                            (f"Publisher-balanced coverage share changed from "
                            f"{previous['share']:.1%} to {current['share']:.1%} "
                            f"({delta:+.2f} percentage points). Distinct events: "
                            f"{previous['events']} to {current['events']}. "
                            "This measures news attention within the monitored corpus."))}
        section = next((k for k, v in SECTION_STATES.items() if v == state), "other_signals")
        result[section].append(item)
    for section in SECTION_STATES:
        result[section].sort(key=lambda item, section=section: (
            -item["share_current"] if section == "new" else -abs(item["delta_pp"]),
            -item["event_count_previous" if section == "trending_down"
                  else "event_count_current"], item["topic_id"]))
    result["other_signals"].sort(key=lambda item: item["topic_id"])
    novelty_reason = next((item["reason"] for item in result["other_signals"]
                           if item["reason"] in {
                               "insufficient_history", "classification_incomplete"}),
                          None)
    result["section_status"] = {section: empty_section(section, reason or (
        (novelty_reason or "insufficient_history") if section == "new" and (
            not history_ready or novelty_reason)
        else "no_qualifying_topics")) for section in SECTION_STATES}
    result["summary"] = (f"News attention for {result['date_from']} to {report_date}: "
                         f"{len(cohort)} comparable publisher groups. "
                         "Share is equally weighted by publisher; it does not measure adoption "
                         "or sentiment.")
    return result
