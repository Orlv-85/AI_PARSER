"""Period AI Signals: bounds, thresholds, input records and status (see signals_period.md)."""
import calendar
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.core.daily.signals_entities import Entity
from app.core.daily.signals_model import ArticleObs, DayCoverage, Thresholds

WEEK = "week"
MONTH = "month"
KINDS = (WEEK, MONTH)


@dataclass(frozen=True)
class PeriodThresholds:  # pylint: disable=too-many-instance-attributes
    kind: str
    min_complete_days: int
    min_items: int
    breadth_ratio: float
    quiet_items: int
    top_max: int
    top_entity_max: int
    top_entity_min_articles: int
    top_entity_min_publishers: int
    new_period_max: int
    links_max: int = 3
    # Month risers and coolers (trend_delta over month totals); None for a week.
    month_rising_min_current: int | None = None
    month_rising_min_delta: int | None = None
    month_rising_ratio: float | None = None
    month_rising_min_publishers: int | None = None
    month_rising_max: int | None = None
    month_cooling_min_previous: int | None = None
    month_cooling_min_delta: int | None = None
    month_cooling_ratio: float | None = None
    month_cooling_min_publishers: int | None = None
    month_cooling_max: int | None = None

    @classmethod
    def for_kind(cls, kind: str) -> PeriodThresholds:
        if kind == WEEK:
            return cls(WEEK, min_complete_days=6, min_items=100, breadth_ratio=0.7,
                       quiet_items=150, top_max=8, top_entity_max=5, top_entity_min_articles=3,
                       top_entity_min_publishers=2, new_period_max=10)
        if kind == MONTH:
            return cls(MONTH, min_complete_days=24, min_items=400, breadth_ratio=0.7,
                       quiet_items=600, top_max=12, top_entity_max=8, top_entity_min_articles=6,
                       top_entity_min_publishers=3, new_period_max=16,
                       month_rising_min_current=12, month_rising_min_delta=8,
                       month_rising_ratio=1.5, month_rising_min_publishers=3,
                       month_rising_max=8, month_cooling_min_previous=15,
                       month_cooling_min_delta=8, month_cooling_ratio=0.5,
                       month_cooling_min_publishers=3, month_cooling_max=6)
        raise ValueError(f"unknown period kind: {kind}")


@dataclass(frozen=True)
class PreviousPeriod:
    """What the comparison needs from the stored previous period of the same kind."""
    status: str
    publishers: int
    event_stories: Mapping[str, int]


@dataclass(frozen=True)
class PeriodInput:  # pylint: disable=too-many-instance-attributes
    kind: str
    start: date
    snapshots: Mapping[date, Mapping[str, Any]]  # stored daily payloads of the period days
    coverage: Mapping[date, DayCoverage]
    observations: Mapping[date, Sequence[ArticleObs]]
    entities: Mapping[str, Entity]
    entity_ids: Mapping[str, int]
    extraction_version: str
    generated_at: datetime
    comparable_from: date
    previous: PreviousPeriod | None = None
    thresholds: PeriodThresholds | None = None
    daily: Thresholds = Thresholds()

    @property
    def limits(self) -> PeriodThresholds:
        return self.thresholds or PeriodThresholds.for_kind(self.kind)

    @property
    def end(self) -> date:
        return period_bounds(self.kind, self.start)[1]

    @property
    def days(self) -> list[date]:
        return period_days(self.kind, self.start)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def period_bounds(kind: str, day: date) -> tuple[date, date]:
    """First and last day (inclusive, UTC digest days) of the period that contains `day`."""
    if kind == WEEK:
        start = week_start(day)
        return start, start + timedelta(days=6)
    if kind == MONTH:
        last = calendar.monthrange(day.year, day.month)[1]
        return day.replace(day=1), day.replace(day=last)
    raise ValueError(f"unknown period kind: {kind}")


def period_days(kind: str, day: date) -> list[date]:
    start, end = period_bounds(kind, day)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def previous_start(kind: str, start: date) -> date:
    """Start of the period before the one that starts on `start`."""
    return period_bounds(kind, start - timedelta(days=1))[0]


def next_start(kind: str, start: date) -> date:
    """Start of the period after the one that starts on `start`."""
    return period_bounds(kind, start)[1] + timedelta(days=1)


def period_status(limits: PeriodThresholds, *, snapshot_days: int, complete_days: int, items: int,
                  previous_ready: bool) -> str:
    """unavailable > partial > building_history > ready. A day without data is not a zero day."""
    if snapshot_days == 0:
        return "unavailable"
    if complete_days < limits.min_complete_days or items < limits.min_items:
        return "partial"
    if not previous_ready:
        return "building_history"
    return "ready"
