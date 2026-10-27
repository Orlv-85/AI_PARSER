"""Fetch cycle value types and tuning constants."""
from dataclasses import dataclass

from app.config.sources import SourceConfig
from app.ingest.html import (
    HtmlListPageResult,
)
from app.ingest.rss import RssItemList

# Pending admission candidates replayed per source before its fresh fetch.
PENDING_REPLAY_LIMIT = 50
# Pending body candidates published longer ago are settled without screening.
PENDING_REPLAY_MAX_AGE_DAYS = 30
# A daily-rubric Comparison answer sets material_type from this confidence on.
COMPARISON_MIN_CONFIDENCE = 0.7

# (source order, config, sources.id, stored fetch state)
EnabledSource = tuple[int, SourceConfig, int, dict[str, object | None]]
type FetchResult = RssItemList | HtmlListPageResult


@dataclass(frozen=True)
class FetchSummary:  # pylint: disable=too-many-instance-attributes
    run_id: str
    source_count: int
    fetched: int
    new: int
    duplicates: int
    errors: int
    not_modified_sources: int = 0
    skipped_known_html_links: int = 0
    early_stop_hits: int = 0
    semantic_rejected: int = 0
    semantic_unresolved: int = 0
    semantic_cache_hits: int = 0
    screening_paused: int = 0
    examined: int = 0
    sources_fetched: int = 0


@dataclass
class SourceMetrics:  # pylint: disable=too-many-instance-attributes
    source_id: str
    source_type: str
    fetched_items: int = 0
    examined_items: int = 0
    new_items: int = 0
    duplicate_items: int = 0
    errors: int = 0
    skipped_known_items: int = 0
    early_stop_hit: bool = False
    not_modified: bool = False
    coverage_complete: bool = True
    acquisition_stopped: bool = False
    semantic_rejected: int = 0
    semantic_unresolved: int = 0
    semantic_cache_hits: int = 0
    screening_paused: bool = False
    replay_items: int = 0


@dataclass
class AdmissionState:
    enabled: bool = False
    paused: bool = False
    fresh_success: bool = False
    cache_hits: int = 0
    rejected: int = 0
    unresolved: int = 0
    observed: int = 0
