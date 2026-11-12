"""Shape of the stored period AI Signals payload (feature doc: signals_period.md).

`compute_period` builds it; the period brief reads it back from JSON.
"""
from typing import TypedDict

from app.core.daily.signals_payload import Link, NewItem, TrendItem


class CoverageLine(TypedDict):
    days: int
    complete_days: int
    missing_days: list[str]
    items: int
    extracted: int
    extracted_share: float | None
    publishers: int
    quiet: bool


class PeriodStory(TypedDict):
    label: str
    event_type: str
    entities: list[str]
    days: list[str]
    articles: int
    publishers: int
    links: list[Link]


class PeriodEntity(TypedDict):
    entity_id: int
    name: str
    type: str
    vendor: str | None
    articles: int
    publishers: int
    days: list[str]
    links: list[Link]


class PeriodNewItem(NewItem):
    first_seen_day: str


class MonthTrendItem(TypedDict):
    """A month Rising or Cooling item: month totals instead of the 7-day counts."""
    entity_id: int
    name: str
    type: str
    vendor: str | None
    current: int
    previous: int
    expected: float
    trailing_mean: None
    spike: bool
    publishers: int
    links: list[Link]


class Trend(TypedDict):
    state: str
    source: str | None
    rising: list[TrendItem] | list[MonthTrendItem]
    cooling: list[TrendItem] | list[MonthTrendItem]


class MixRow(TypedDict):
    event_type: str
    label: str
    stories: int
    articles: int
    previous_stories: int | None
    delta: int | None


class MixMore(TypedDict):
    types: int
    stories: int
    articles: int


class EventMix(TypedDict):
    types: list[MixRow]
    more: MixMore
    stories_by_type: dict[str, int]


class Comparison(TypedDict):
    state: str
    reason: str | None
    previous_publishers: int | None
    publisher_ratio: float | None


class PeriodPayload(TypedDict):
    period_kind: str
    period_start: str
    period_end: str
    status: str
    methodology_version: str
    daily_methodology_version: str
    extraction_version: str
    generated_at: str
    thresholds: dict[str, object]
    coverage: CoverageLine
    quiet: bool
    comparison: Comparison
    sections: dict[str, str]
    top_stories: list[PeriodStory]
    top_entities: dict[str, list[PeriodEntity]]
    new: list[PeriodNewItem]
    rising: list[TrendItem] | list[MonthTrendItem]
    cooling: list[TrendItem] | list[MonthTrendItem]
    trend_source: str | None
    event_mix: EventMix
