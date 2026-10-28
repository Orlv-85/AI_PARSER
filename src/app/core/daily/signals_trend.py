"""Daily AI Signals: the Rising/Cooling window computation, shared with the period signals.

Feature doc: signals.md. Pure; no behavior of its own beyond what the daily snapshot used before the
move (the payload hashes of the 006 fixtures are unchanged).
"""
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.daily.signals_model import ArticleObs, DayCoverage, Thresholds
from app.core.daily.signals_naming import unit_key


@dataclass(frozen=True)
class TrendRow:  # pylint: disable=too-many-instance-attributes
    """One entity unit that passes the Rising and/or Cooling rule."""
    unit: str
    current: int
    previous: int
    expected: float
    current_articles: Sequence[ArticleObs]
    previous_articles: Sequence[ArticleObs]
    rising: bool
    cooling: bool

    @property
    def rising_delta(self) -> float:
        return self.current - self.expected

    @property
    def cooling_delta(self) -> float:
        return self.expected - self.current


def unit_articles(articles: Iterable[ArticleObs]) -> dict[str, list[ArticleObs]]:
    out: dict[str, list[ArticleObs]] = defaultdict(list)
    for a in articles:
        for unit in sorted({unit_key(m.entity_key) for m in a.mentions}):
            out[unit].append(a)
    return out


def window_units(observations: Mapping[date, Sequence[ArticleObs]], days: Iterable[date]
                 ) -> dict[str, list[ArticleObs]]:
    out: dict[str, list[ArticleObs]] = defaultdict(list)
    for day in days:
        for unit, articles in unit_articles(observations.get(day, ())).items():
            out[unit].extend(articles)
    return out


def trend_windows(day: date, coverage: Mapping[date, DayCoverage], comparable_from: date,
                  t: Thresholds) -> tuple[list[date], list[date]] | None:
    """The last `window_days` days ending on `day` (day included) and the `window_days` before.

    None when the previous window starts before `comparable_from`, a window has fewer than
    `window_min_complete` complete days, or a window has no extracted item.
    """
    w = t.window_days
    current = [day - timedelta(days=i) for i in range(w)]
    previous = [day - timedelta(days=i) for i in range(w, 2 * w)]
    if min(previous) < comparable_from:
        return None
    cur = [d for d in current if _complete(coverage, d, t)]
    prev = [d for d in previous if _complete(coverage, d, t)]
    if len(cur) < t.window_min_complete or len(prev) < t.window_min_complete:
        return None
    if not _extracted(coverage, cur) or not _extracted(coverage, prev):
        return None
    return cur, prev


def _complete(coverage: Mapping[date, DayCoverage], day: date, t: Thresholds) -> bool:
    cov = coverage.get(day)
    return cov is not None and cov.complete(t.complete_ratio)


def _extracted(coverage: Mapping[date, DayCoverage], days: Iterable[date]) -> int:
    return sum(coverage[d].extracted for d in days)


def trend_delta(coverage: Mapping[date, DayCoverage], cur_days: Sequence[date],
                prev_days: Sequence[date], *, cur_units: Mapping[str, Sequence[ArticleObs]],
                prev_units: Mapping[str, Sequence[ArticleObs]], excluded: set[str],
                t: Thresholds) -> list[TrendRow]:
    """Units passing the Rising or Cooling rule; `expected` is the previous count scaled by volume.

    Rows come in unit order; ordering by delta and the entity filters stay with the caller.
    """
    ratio = _extracted(coverage, cur_days) / _extracted(coverage, prev_days)
    rows = []
    for unit in sorted(set(cur_units) | set(prev_units)):
        if unit in excluded:
            continue
        cur_a, prev_a = cur_units.get(unit, []), prev_units.get(unit, [])
        cur, prev = len(cur_a), len(prev_a)
        expected = prev * ratio
        rising = (cur >= t.rising_min_current and cur - expected >= t.rising_min_delta
                  and cur >= t.rising_ratio * max(expected, 1)
                  and len({a.publisher for a in cur_a}) >= t.rising_min_publishers)
        cooling = (prev >= t.cooling_min_previous and expected - cur >= t.cooling_min_delta
                   and cur <= t.cooling_ratio * expected
                   and len({a.publisher for a in prev_a}) >= t.cooling_min_publishers)
        if rising or cooling:
            rows.append(TrendRow(unit, cur, prev, expected, cur_a, prev_a, rising, cooling))
    return rows
