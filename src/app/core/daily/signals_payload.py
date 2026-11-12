"""Shape of the stored daily AI Signals payload (feature doc: src/app/usecases/daily/signals.md).

`compute_snapshot` builds it; the brief and the period computation read it back from JSON.
Keys that methodology v1 did not write are `NotRequired`: stored v1 payloads are read too.
"""
from typing import NotRequired, TypedDict


class Link(TypedDict):
    title: str
    url: str
    publisher: str


class Section(TypedDict):
    state: str
    note: str | None


class Coverage(TypedDict):
    items: int
    matched: int
    extracted: int
    failed: int
    skipped: int
    pending: int
    unmatched: int


class NewItem(TypedDict):
    entity_id: int
    name: str
    type: str
    vendor: str | None
    level: str
    variant_of: str | None
    variants: list[str]
    novelty_quote: str
    one_liner: NotRequired[str | None]
    one_liner_source: NotRequired[str | None]
    articles: int
    publishers: int
    links: list[Link]
    spikes: NotRequired[list[str]]


class TrendItem(TypedDict):
    """A Rising, Cooling or spike item; counts are None where the item has none."""
    entity_id: int
    name: str
    type: str
    vendor: str | None
    current_7d: int | None
    previous_7d: int | None
    expected_7d: float | None
    trailing_mean: float | None
    spike: bool
    today: int
    publishers: int
    links: list[Link]
    reason: NotRequired[str | None]
    spikes: NotRequired[list[str]]


class TopStory(TypedDict):
    label: str
    event_type: str
    articles: int
    publishers: int
    entities: list[str]
    spikes: NotRequired[list[str]]
    links: list[Link]


class EventCount(TypedDict):
    event_type: str
    label: str
    stories: int
    articles: int
    links: list[Link]


class Suppressed(TypedDict):
    name: str
    entity_id: int
    reason: str
    day: NotRequired[str]
    match: NotRequired[str]
    text: NotRequired[str]


class Hidden(TypedDict):
    name: str
    entity_id: int


class Folded(TypedDict):
    name: str
    into: str | None
    reason: str


class SnapshotPayload(TypedDict):
    report_date: str
    status: str
    methodology_version: str
    extraction_version: str
    generated_at: str
    novelty_history_days: int
    comparable_complete_days: int
    coverage: Coverage
    notes: list[str]
    sections: dict[str, Section]
    thresholds: dict[str, object]
    quiet: NotRequired[bool]
    new: list[NewItem]
    new_suppressed: NotRequired[list[Suppressed]]
    new_hidden: NotRequired[list[Hidden]]
    top_stories: list[TopStory]
    rising: list[TrendItem]
    spikes_folded: NotRequired[list[Folded]]
    cooling: list[TrendItem]
    event_counts: list[EventCount]
    article_event_types: dict[str, str]
