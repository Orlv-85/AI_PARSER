"""Daily AI Signals: constants, thresholds and input records of the snapshot (see signals.md)."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from app.core.daily.signals_brief import HARD_EVENTS
from app.core.daily.signals_entities import Entity
from app.core.daily.signals_history import LexicalHistory

EVENT_LABELS = {
    "model_release": "model releases", "product_launch": "product launches",
    "funding": "funding rounds", "acquisition": "acquisitions", "partnership": "partnerships",
    "infrastructure_deal": "infrastructure deals", "hardware": "hardware",
    "regulation_policy": "regulation & policy", "legal": "legal",
    "security_incident": "security incidents", "people_move": "people moves",
    "benchmark_result": "benchmark results", "research": "research",
    "opinion_analysis": "analysis", "other": "other",
}


EVENT_FAMILY = {"model_release": "launch", "product_launch": "launch"}


# Display order of New items within a level (CP1, gate finding 6).
EARLY_TYPE_ORDER = ("model", "hardware", "benchmark", "dataset", "technology", "company", "product",
                    "policy")


CONFIRMED_TYPE_ORDER = ("model", "product", "hardware", "company", "technology", "policy",
                        "benchmark", "dataset")


@dataclass(frozen=True)
class Thresholds:  # pylint: disable=too-many-instance-attributes
    new_max: int = 8
    confirmed_publishers: int = 2
    history_note_days: int = 30
    top_max: int = 5
    top_min_publishers: int = 2
    links_max: int = 3
    complete_ratio: float = 0.9
    spike_min_articles: int = 3
    spike_min_publishers: int = 2
    spike_ratio: float = 3.0
    spike_mean_floor: float = 1 / 3
    spike_trailing_days: int = 7
    spike_min_trailing_days: int = 3
    spike_trailing_min_items: int = 10
    quiet_items: int = 20
    one_liner_max: int = 140
    fold_share: float = 0.5
    diffuse_story_min: int = 2
    chip_hard_events: tuple[str, ...] = HARD_EVENTS
    window_days: int = 7
    window_min_complete: int = 6
    rising_min_current: int = 4
    rising_min_delta: int = 3
    rising_ratio: float = 1.5
    rising_min_publishers: int = 2
    rising_max: int = 6
    cooling_min_previous: int = 5
    cooling_min_delta: int = 3
    cooling_ratio: float = 0.5
    cooling_min_publishers: int = 2
    cooling_max: int = 4


@dataclass(frozen=True)
class EntityMention:
    entity_key: str
    type_group: str
    base_key: str
    role: str
    is_new: bool = False
    novelty_quote: str | None = None


@dataclass(frozen=True)
class ArticleObs:  # pylint: disable=too-many-instance-attributes
    article_id: int
    scope_day: date
    title: str
    url: str
    publisher: str
    published_at: datetime | None
    event_type: str
    mentions: tuple[EntityMention, ...] = ()
    summary: str = ""  # the digest item summary of this day's item URL


@dataclass(frozen=True)
class DayCoverage:  # pylint: disable=too-many-instance-attributes
    day: date
    kind: str  # signals | history
    published: bool
    items: int = 0
    matched: int = 0
    extracted: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def pending(self) -> int:
        return max(0, self.matched - self.extracted - self.failed - self.skipped)

    def complete(self, ratio: float = Thresholds.complete_ratio) -> bool:
        return self.published and (self.items == 0 or self.extracted >= ratio * self.items)


@dataclass(frozen=True)
class SnapshotInput:  # pylint: disable=too-many-instance-attributes
    day: date
    observations: Mapping[date, Sequence[ArticleObs]]
    coverage: Mapping[date, DayCoverage]
    entities: Mapping[str, Entity]
    entity_ids: Mapping[str, int]
    extraction_version: str
    generated_at: datetime
    comparable_from: date
    thresholds: Thresholds = Thresholds()
    history: LexicalHistory | None = None
