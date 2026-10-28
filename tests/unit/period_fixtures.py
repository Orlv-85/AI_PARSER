"""Fixture weeks for the period signals tests, built from tests/fixtures/daily_signals/.

The previous week is the same fixture days shifted back by seven days with every other article
dropped; Saturday and Sunday are fixture articles re-dated, so the week has 7 days with data.
"""
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from app.core.daily.signals_compute import compute_snapshot
from app.core.daily.signals_entities import Mention, reconcile
from app.core.daily.signals_model import (
    ArticleObs,
    DayCoverage,
    EntityMention,
    SnapshotInput,
    Thresholds,
)
from app.core.periodic.period_model import PeriodInput, PreviousPeriod

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "daily_signals"
WEEK = date(2026, 10, 12)
PREVIOUS_WEEK = date(2026, 10, 5)
COMPARABLE_FROM = date(2026, 9, 1)  # lets the fixture week have a previous week
GENERATED = datetime(2026, 10, 19, 2, 30)


def _raw():
    mentions, rows = [], []
    for path in sorted(FIXTURES.glob("signals_*.json")):
        data = json.loads(path.read_text())
        day = date.fromisoformat(data["day"])
        for article in data["articles"]:
            ids = []
            for entity in article["entities"]:
                mentions.append(Mention(
                    mention_id=len(mentions) + 1, scope_day=day, article_id=article["article_id"],
                    publisher=article["publisher"], name=entity["name"],
                    canonical_name=entity["canonical"] or entity["name"],
                    entity_type=entity["type"], vendor=entity["vendor"], role=entity["role"]))
                ids.append(len(mentions))
            rows.append((day, article, ids))
    return mentions, rows


def fixture_world():
    """(observations by day for both weeks, reconciliation) from the five fixture days."""
    mentions, rows = _raw()
    out_mentions: list[Mention] = []
    plan = []  # (new day, article dict, article id, mention rows)
    next_id = 100000

    def add(day, article, ids):
        nonlocal next_id
        next_id += 1
        new_ids = []
        for i in ids:
            m = mentions[i - 1]
            out_mentions.append(replace(m, mention_id=len(out_mentions) + 1, scope_day=day,
                                        article_id=next_id))
            new_ids.append(len(out_mentions))
        plan.append((day, article, next_id, new_ids))

    for day, article, ids in rows:
        add(day, article, ids)
    for number, (day, article, ids) in enumerate(rows):
        if number % 2 == 0:
            add(day - timedelta(days=7), article, ids)
    by_weekday = {d.weekday(): [r for r in rows if r[0] == d] for d in sorted({r[0] for r in rows})}
    monday = by_weekday[0]
    for base in (WEEK, PREVIOUS_WEEK):
        for offset in (5, 6):
            for _day, article, ids in monday[:14]:
                add(base + timedelta(days=offset), article, ids)
    result = reconcile(out_mentions)
    days: dict[date, list[ArticleObs]] = {}
    for day, article, article_id, ids in plan:
        days.setdefault(day, []).append(ArticleObs(
            article_id=article_id, scope_day=day, title=article["title"], url=article["url"],
            publisher=article["publisher"],
            published_at=datetime.fromisoformat(article["published_at"])
            if article["published_at"] else None,
            event_type=article["event_type"],
            mentions=tuple(EntityMention(result.assignments[i], result.keys[i].type_group,
                                         result.keys[i].base_key, out_mentions[i - 1].role)
                           for i in ids)))
    return days, result


def fixture_period_input(*, with_previous: bool = True, **overrides) -> PeriodInput:
    days, result = fixture_world()
    coverage = {d: DayCoverage(day=d, kind="signals", published=True, items=len(a), matched=len(a),
                               extracted=len(a)) for d, a in days.items()}
    ids = {key: n for n, key in enumerate(sorted(result.entities), start=1)}
    snapshots = {}
    for day in days:
        snapshots[day] = compute_snapshot(SnapshotInput(
            day=day, observations=days, coverage=coverage, entities=result.entities,
            entity_ids=ids, extraction_version="daily-signals-extract-5", generated_at=GENERATED,
            comparable_from=COMPARABLE_FROM, thresholds=Thresholds()))
    before = {a.publisher for d, found in days.items() if d < WEEK for a in found}
    previous = PreviousPeriod("ready", len(before), {}) if with_previous else None
    data = PeriodInput(
        kind="week", start=WEEK, snapshots=snapshots, coverage=coverage, observations=days,
        entities=result.entities, entity_ids=ids, extraction_version="daily-signals-extract-5",
        generated_at=GENERATED, comparable_from=COMPARABLE_FROM, previous=previous)
    return replace(data, **overrides) if overrides else data


def synthetic(snapshots, *, start=WEEK, kind="week", items=20, **overrides) -> PeriodInput:
    """A period whose days have the given snapshot dicts and `items` complete items each."""
    coverage = {d: DayCoverage(day=d, kind="signals", published=True, items=items, matched=items,
                               extracted=items) for d in snapshots}
    data = PeriodInput(
        kind=kind, start=start, snapshots=snapshots, coverage=coverage, observations={},
        entities={}, entity_ids={}, extraction_version="x", generated_at=GENERATED,
        comparable_from=COMPARABLE_FROM)
    return replace(data, **overrides) if overrides else data
