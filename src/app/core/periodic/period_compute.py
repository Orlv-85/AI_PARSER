"""Period AI Signals computation: sums and comparisons of the daily data (see signals_period.md).

Pure and deterministic: no database, no provider, no clock. `generated_at` is an input.
"""
import copy
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, replace
from datetime import date
from typing import Any

from app.core.daily.signals_brief import HARD_EVENTS
from app.core.daily.signals_compute import METHODOLOGY_VERSION, payload_hash
from app.core.daily.signals_model import EVENT_LABELS, ArticleObs, Thresholds
from app.core.daily.signals_naming import unit_key
from app.core.daily.signals_stories import _article_order, links
from app.core.daily.signals_trend import (
    TrendRow,
    trend_delta,
    trend_windows,
    unit_articles,
    window_units,
)
from app.core.periodic.period_model import (
    MONTH,
    PeriodInput,
    PeriodThresholds,
    period_days,
    period_status,
    previous_start,
)

__all__ = ["PERIOD_METHODOLOGY_VERSION", "compute_period", "payload_hash"]

PERIOD_METHODOLOGY_VERSION = "period-signals-1"

ENTITY_GROUPS = (("model", "models"), ("product", "products"), ("company", "companies"),
                 ("technology", "technologies"))


def _r(value: float) -> float:
    return round(value, 3)


def _articles(data: PeriodInput) -> list[ArticleObs]:
    out: list[ArticleObs] = []
    for day in data.days:
        out.extend(sorted(data.observations.get(day, ()), key=_article_order))
    return out


def _snapshots(data: PeriodInput) -> list[tuple[date, Mapping[str, Any]]]:
    return [(d, data.snapshots[d]) for d in data.days
            if d in data.snapshots and data.snapshots[d].get("status") != "unavailable"]


# Coverage -------------------------------------------------------------------------------------
def coverage_line(data: PeriodInput, articles: Sequence[ArticleObs]) -> dict[str, Any]:
    """Days complete / days in period, items, extracted share, publishers, quiet flag.

    A day without a coverage row is missing: it is listed, never counted as a zero day."""
    t, daily = data.limits, data.daily
    known = [data.coverage[d] for d in data.days if d in data.coverage]
    complete = [c.day for c in known if c.kind == "signals" and c.complete(daily.complete_ratio)]
    items = sum(c.items for c in known)
    extracted = sum(c.extracted for c in known)
    return {
        "days": len(data.days),
        "complete_days": len(complete),
        "missing_days": [d.isoformat() for d in data.days if d not in data.coverage],
        "items": items,
        "extracted": extracted,
        "extracted_share": _r(extracted / items) if items else None,
        "publishers": len({a.publisher for a in articles}),
        "quiet": items < t.quiet_items,
    }


# Top stories ----------------------------------------------------------------------------------
def top_stories(data: PeriodInput) -> list[dict[str, Any]]:
    """Daily top stories merged across days by event type + entity set; ranked by distinct
    publishers (a lower bound from the stored links), then days."""
    t = data.limits
    merged: dict[tuple, dict[str, Any]] = {}
    for day, snap in _snapshots(data):
        for story in snap.get("top_stories", ()):
            entities = tuple(sorted(story.get("entities", ())))
            key = (story["event_type"], entities or ("label", story["label"].casefold()))
            row = merged.setdefault(key, {
                "label": story["label"], "event_type": story["event_type"],
                "entities": list(entities), "days": [], "articles": 0, "_pubs": set(),
                "_best": -1, "_links": {}})
            row["days"].append(day.isoformat())
            row["articles"] += story["articles"]
            row["_best"] = max(row["_best"], story["publishers"])
            if story["publishers"] > row.get("_label_pubs", -1):
                row["label"], row["_label_pubs"] = story["label"], story["publishers"]
            for link in story.get("links", ()):
                row["_pubs"].add(link["publisher"])
                row["_links"].setdefault(link["url"], link)
    out = []
    for row in merged.values():
        row["publishers"] = max(row.pop("_best"), len(row.pop("_pubs")))
        row.pop("_label_pubs", None)
        row["links"] = _pick_links(list(row.pop("_links").values()), t.links_max)
        row["days"] = sorted(row["days"])
        out.append(row)
    out.sort(key=lambda r: (-r["publishers"], -len(r["days"]), -r["articles"], r["label"]))
    return out[:t.top_max]


def _pick_links(items: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    first: list[dict[str, str]] = []
    rest: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        (rest if item["publisher"] in seen else first).append(item)
        seen.add(item["publisher"])
    return (first + rest)[:limit]


# Top entities ---------------------------------------------------------------------------------
def top_entities(data: PeriodInput, articles: Sequence[ArticleObs]) -> dict[str, list[dict]]:
    """By type group: distinct articles, then publishers; minimums and a cap per group."""
    t = data.limits
    by_key: dict[str, dict[int, ArticleObs]] = defaultdict(dict)
    for a in articles:
        for m in a.mentions:
            by_key[m.entity_key][a.article_id] = a
    groups: dict[str, list[dict[str, Any]]] = {name: [] for _, name in ENTITY_GROUPS}
    names = dict(ENTITY_GROUPS)
    for key, members in by_key.items():
        entity = data.entities.get(key)
        if entity is None or entity.needs_review or entity.entity_type not in names:
            continue
        found = list(members.values())
        publishers = len({a.publisher for a in found})
        if len(found) < t.top_entity_min_articles or publishers < t.top_entity_min_publishers:
            continue
        groups[names[entity.entity_type]].append({
            "entity_id": data.entity_ids.get(key, 0), "name": entity.display_name,
            "type": entity.entity_type, "vendor": entity.vendor, "articles": len(found),
            "publishers": publishers,
            "days": sorted({a.scope_day.isoformat() for a in found}),
            "links": links(found, t.links_max)})
    for items in groups.values():
        items.sort(key=lambda i: (-i["articles"], -i["publishers"], i["name"], i["entity_id"]))
    return {name: items[:t.top_entity_max] for name, items in groups.items()}


# New ------------------------------------------------------------------------------------------
def new_this_period(data: PeriodInput) -> list[dict[str, Any]]:
    """Union of the daily New lists: confirmed first, then by first-seen day."""
    t = data.limits
    seen: dict[Any, dict[str, Any]] = {}
    for day, snap in _snapshots(data):
        for item in snap.get("new", ()):
            key = item.get("entity_id") or item["name"].casefold()
            row = seen.get(key)
            if row is None:
                seen[key] = {**copy.deepcopy(dict(item)), "first_seen_day": day.isoformat()}
            elif item["level"] == "confirmed" and row["level"] != "confirmed":
                seen[key] = {**copy.deepcopy(dict(item)), "first_seen_day": row["first_seen_day"]}
    rows = list(seen.values())
    rows.sort(key=lambda r: (r["level"] != "confirmed", r["first_seen_day"], -r["publishers"],
                             r["name"]))
    return rows[:t.new_period_max]


# Rising and cooling ---------------------------------------------------------------------------
def risers_and_coolers(data: PeriodInput) -> dict[str, Any]:
    """Week: the daily computation with D = the last day of the week. The Sunday snapshot is used
    when its methodology is current and its Rising was usable, else the shared helper runs over
    the week bounds. Month: the shared rule over month totals against the previous month."""
    if data.kind == MONTH:
        return _month_risers(data)
    end = data.end
    snap = data.snapshots.get(end)
    if snap is not None and snap.get("methodology_version") == METHODOLOGY_VERSION:
        if snap.get("sections", {}).get("rising", {}).get("state") == "ready":
            return {"state": "ready", "source": "sunday_snapshot",
                    "rising": copy.deepcopy(list(snap.get("rising", ()))),
                    "cooling": copy.deepcopy(list(snap.get("cooling", ())))}
    return _risers_from_helper(data)


def _risers_from_helper(data: PeriodInput) -> dict[str, Any]:
    daily = data.daily
    usable = trend_windows(data.end, data.coverage, data.comparable_from, daily)
    if usable is None:
        return {"state": "unavailable", "source": "helper", "rising": [], "cooling": []}
    cur_days, prev_days = usable
    today = unit_articles(data.observations.get(data.end, ()))
    rows = trend_delta(data.coverage, cur_days, prev_days,
                       cur_units=window_units(data.observations, cur_days),
                       prev_units=window_units(data.observations, prev_days),
                       excluded=set(), t=daily)

    def counts(row: TrendRow) -> dict[str, Any]:
        return {"current_7d": row.current, "previous_7d": row.previous,
                "expected_7d": _r(row.expected), "today": len(today.get(row.unit, ()))}

    rising, cooling = _ranked(data, rows, cur_days, prev_days, counts_of=counts,
                              keys=("current_7d", "previous_7d"))
    return {"state": "ready", "source": "helper", "rising": rising[:daily.rising_max],
            "cooling": cooling[:daily.cooling_max]}


def _month_thresholds(data: PeriodInput) -> Thresholds:
    """The daily rule with the month minimums of `PeriodThresholds` (counts are month totals)."""
    t = data.limits
    return replace(
        data.daily, rising_min_current=t.month_rising_min_current,
        rising_min_delta=t.month_rising_min_delta, rising_ratio=t.month_rising_ratio,
        rising_min_publishers=t.month_rising_min_publishers, rising_max=t.month_rising_max,
        cooling_min_previous=t.month_cooling_min_previous,
        cooling_min_delta=t.month_cooling_min_delta, cooling_ratio=t.month_cooling_ratio,
        cooling_min_publishers=t.month_cooling_min_publishers, cooling_max=t.month_cooling_max)


def _month_windows(data: PeriodInput) -> tuple[list[date], list[date]] | None:
    """Complete days of this month and of the previous one; None when the previous month starts
    before the comparable range, a month has fewer than `min_complete_days` complete days or no
    extracted item."""
    t, daily = data.limits, data.daily
    before = period_days(MONTH, previous_start(MONTH, data.start))
    if before[0] < data.comparable_from:
        return None

    def complete(days: list[date]) -> list[date]:
        return [d for d in days if d in data.coverage and data.coverage[d].kind == "signals"
                and data.coverage[d].complete(daily.complete_ratio)]

    cur, prev = complete(data.days), complete(before)
    if min(len(cur), len(prev)) < t.min_complete_days:
        return None
    if not sum(data.coverage[d].extracted for d in cur) or not sum(
            data.coverage[d].extracted for d in prev):
        return None
    return cur, prev


def _month_risers(data: PeriodInput) -> dict[str, Any]:
    windows = _month_windows(data)
    if windows is None:
        return {"state": "unavailable", "source": "month_helper", "rising": [], "cooling": []}
    cur_days, prev_days = windows
    daily = _month_thresholds(data)
    rows = trend_delta(data.coverage, cur_days, prev_days,
                       cur_units=window_units(data.observations, cur_days),
                       prev_units=window_units(data.observations, prev_days),
                       excluded=set(), t=daily)

    def counts(row: TrendRow) -> dict[str, Any]:
        return {"current": row.current, "previous": row.previous, "expected": _r(row.expected)}

    rising, cooling = _ranked(data, rows, cur_days, prev_days, counts_of=counts,
                              keys=("current", "previous"))
    return {"state": "ready", "source": "month_helper", "rising": rising[:daily.rising_max],
            "cooling": cooling[:daily.cooling_max]}


def _ranked(data: PeriodInput, rows: Sequence[TrendRow], cur_days: Sequence[date],
            prev_days: Sequence[date], *, counts_of: Callable[[TrendRow], dict[str, Any]],
            keys: tuple[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rising and cooling items, best first; `keys` are the current and previous count fields."""
    cur_key, prev_key = keys
    rising: list[dict[str, Any]] = []
    cooling: list[dict[str, Any]] = []
    for row in rows:
        counts = counts_of(row)
        if row.rising:
            item = _trend_item(data, row.unit, cur_days, row.current_articles, counts)
            if item is not None:
                rising.append({**item, "_delta": row.rising_delta})
        if row.cooling:
            item = _trend_item(data, row.unit, prev_days, row.previous_articles, counts)
            if item is not None:
                cooling.append({**item, "_delta": row.cooling_delta})
    rising.sort(key=lambda i: (-i["_delta"], -i[cur_key], i["name"]))
    cooling.sort(key=lambda i: (-i["_delta"], -i[prev_key], i["name"]))
    for item in rising + cooling:
        item.pop("_delta")
    return rising, cooling


def _trend_item(data: PeriodInput, unit: str, days: Iterable[date],
                articles: Sequence[ArticleObs], counts: dict[str, Any]) -> dict[str, Any] | None:
    seen: Counter[str] = Counter()
    for day in days:
        for a in data.observations.get(day, ()):
            seen.update({m.entity_key for m in a.mentions if unit_key(m.entity_key) == unit})
    key = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    entity = data.entities[key]
    if entity.needs_review:
        return None
    return {"entity_id": data.entity_ids.get(key, 0), "name": entity.display_name,
            "type": entity.entity_type, "vendor": entity.vendor, **counts,
            "trailing_mean": None, "spike": False, "publishers": len({a.publisher
                                                                       for a in articles}),
            "links": links(articles, data.daily.links_max)}


# Event mix ------------------------------------------------------------------------------------
def event_mix(data: PeriodInput, compare: bool) -> dict[str, Any]:
    """Stories and articles per event type from the daily chips; the rest as "+N more"."""
    stories: Counter[str] = Counter()
    arts: Counter[str] = Counter()
    for _, snap in _snapshots(data):
        for chip in snap.get("event_counts", ()):
            stories[chip["event_type"]] += chip["stories"]
            arts[chip["event_type"]] += chip["articles"]
    previous = data.previous.event_stories if compare and data.previous else None
    rows = []
    for event, label in EVENT_LABELS.items():
        if event not in HARD_EVENTS or not (stories[event] or arts[event]):
            continue
        rows.append({"event_type": event, "label": label,
                     "stories": stories[event], "articles": arts[event],
                     "previous_stories": previous.get(event, 0) if previous is not None else None,
                     "delta": stories[event] - previous.get(event, 0)
                     if previous is not None else None})
    rest = [e for e in EVENT_LABELS if e not in HARD_EVENTS and (stories[e] or arts[e])]
    return {"types": rows, "more": {"types": len(rest), "stories": sum(stories[e] for e in rest),
                                    "articles": sum(arts[e] for e in rest)},
            "stories_by_type": {e: stories[e] for e in EVENT_LABELS if stories[e]}}


# Comparison -----------------------------------------------------------------------------------
def comparison(data: PeriodInput, publishers: int) -> dict[str, Any]:
    """`none` without a usable previous period, `suppressed` (low_publisher_coverage) when the
    publishers of this period are below `breadth_ratio` of the previous one, else `ready`."""
    prev = data.previous
    if prev is None or prev.status not in ("ready", "building_history"):
        return {"state": "none", "reason": "no_previous_period", "previous_publishers": None,
                "publisher_ratio": None}
    ratio = publishers / prev.publishers if prev.publishers else None
    if ratio is not None and ratio < data.limits.breadth_ratio:
        return {"state": "suppressed", "reason": "low_publisher_coverage",
                "previous_publishers": prev.publishers, "publisher_ratio": _r(ratio)}
    return {"state": "ready", "reason": None, "previous_publishers": prev.publishers,
            "publisher_ratio": _r(ratio) if ratio is not None else None}


# Payload --------------------------------------------------------------------------------------
def compute_period(data: PeriodInput) -> dict[str, Any]:
    """The stored payload of one completed period."""
    t: PeriodThresholds = data.limits
    articles = _articles(data)
    cov = coverage_line(data, articles)
    snaps = _snapshots(data)
    previous_usable = data.previous is not None and data.previous.status in (
        "ready", "building_history")
    status = period_status(t, snapshot_days=len(snaps), complete_days=cov["complete_days"],
                           items=cov["items"], previous_ready=previous_usable)
    cmp_ = comparison(data, cov["publishers"])
    compared = cmp_["state"] == "ready"
    trend = risers_and_coolers(data) if compared else {
        "state": "hidden", "source": None, "rising": [], "cooling": []}
    mix = event_mix(data, compared)
    sections = {
        "top_stories": "ready" if snaps else "empty",
        "top_entities": "ready" if snaps else "empty",
        "new": "ready" if snaps else "empty",
        "rising": trend["state"],
        "cooling": trend["state"],
        "event_mix": "ready" if snaps else "empty",
    }
    return {
        "period_kind": data.kind,
        "period_start": data.start.isoformat(),
        "period_end": data.end.isoformat(),
        "status": status,
        "methodology_version": PERIOD_METHODOLOGY_VERSION,
        "daily_methodology_version": METHODOLOGY_VERSION,
        "extraction_version": data.extraction_version,
        "generated_at": data.generated_at.isoformat(),
        "thresholds": {k: _r(v) if isinstance(v, float) else v for k, v in asdict(t).items()
                       if data.kind == MONTH or not k.startswith("month_")},
        "coverage": cov,
        "quiet": cov["quiet"],
        "comparison": cmp_,
        "sections": sections,
        "top_stories": top_stories(data),
        "top_entities": top_entities(data, articles),
        "new": new_this_period(data),
        "rising": trend["rising"],
        "cooling": trend["cooling"],
        "trend_source": trend["source"],
        "event_mix": mix,
    }

