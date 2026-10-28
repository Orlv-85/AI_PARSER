from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebUpdateSettings(BaseModel):
    update_execution_mode: Literal["thread", "process"] = "thread"
    request_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    per_source_min_interval_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    concurrency_limit: int = Field(default=8, ge=1, le=64)
    fetch_http_max_connections: int | None = Field(default=20, ge=1, le=256)
    fetch_http_max_keepalive_connections: int | None = Field(default=10, ge=0, le=256)
    rss_known_streak_stop: int = Field(default=20, ge=0, le=500)
    html_known_streak_stop: int = Field(default=20, ge=0, le=500)
    html_max_links_per_source: int | None = Field(default=50, ge=1, le=500)
    article_batch_upsert_enabled: bool = False
    fetch_emit_source_metrics: bool = True


class UpdateStatus(BaseModel):
    run_id: str | None = None
    status: Literal["idle", "running", "finished", "failed"] = "idle"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    source_count: int = 0
    fetched: int = 0
    new: int = 0
    duplicates: int = 0
    errors: int = 0
    error_message: str | None = None
    screening_paused: bool = False
    screening_message: str | None = None


class NewsCollectionStatusResponse(BaseModel):
    paused: bool
    message: str | None = None


class ArticleEvidenceFields(BaseModel):
    publication_day: date | None = None
    publication_status: str | None = None
    publication_precision: str | None = None
    publication_literal: str | None = None
    modified_at: datetime | None = None
    material_type: str | None = None
    compared_products: list[str] = Field(default_factory=list)


class NewsItem(ArticleEvidenceFields):
    title: str
    published_at: datetime | None
    rank_score: float
    url_canonical: str
    source_id: int | None = None
    source_key: str | None = None
    source_name: str | None = None
    category: str | None = None
    category_confidence: float | None = None


class NewsArticleDetail(ArticleEvidenceFields):
    article_id: int
    title: str
    summary: str | None = None
    content: str | None = None
    published_at: datetime | None
    rank_score: float
    url: str
    url_canonical: str
    source_id: int | None = None
    source_key: str | None = None
    source_name: str | None = None


class DigestLinkFeedItem(ArticleEvidenceFields):
    article_id: int
    title: str
    published_at: datetime | None
    url: str
    url_canonical: str
    source_id: int | None = None
    source_key: str | None = None
    source_name: str | None = None
    summary: str | None = None
    content: str | None = None
    category: str | None = None
    category_confidence: float | None = None
    rank_score: float | None = None


class NewsDigestItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=2000)
    url: HttpUrl


class NewsDigestGroupPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    items: list[NewsDigestItemPayload] = Field(min_length=1)


class NewsDigestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_date: date
    groups: list[NewsDigestGroupPayload] = Field(min_length=1)


class NewsDigestResponse(BaseModel):
    report_date: date
    groups: list[NewsDigestGroupPayload]


class WeeklyEvidence(BaseModel):
    id: str
    article_id: int | None = None
    event_id: str
    title: str
    url: HttpUrl
    publisher: str
    published_at: datetime | None = None
    calendar_date: date | None = None
    publication_precision: str | None = None
    publication_interval: dict | None = None
    window: Literal["current", "previous"]
    excerpt: str


class WeeklyAnalyticsItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=2000)
    url: HttpUrl | Literal[""] = ""
    topic_id: str | None = None
    state: Literal[
        "new", "up", "down", "stable", "resurfacing", "insufficient_evidence"
    ] | None = None
    reason: str | None = None
    event_count_current: int | None = None
    event_count_previous: int | None = None
    observed_event_count_current: int | None = None
    observed_event_count_previous: int | None = None
    publisher_count_current: int | None = None
    publisher_count_previous: int | None = None
    share_current: float | None = None
    share_previous: float | None = None
    delta_pp: float | None = None
    growth_pct: float | None = None
    first_observed_at: datetime | None = None
    evidence: list[WeeklyEvidence] = Field(default_factory=list)
    claims: list[dict] = Field(default_factory=list)
    narrative_mode: Literal["deepseek", "template"] = "template"
    narrative_reason: str | None = None
    narrative_support: list[dict] = Field(default_factory=list)
    narrative_diagnostics: list[dict] = Field(default_factory=list)


class WeeklyAnalyticsResponse(BaseModel):
    report_date: date
    date_from: date
    date_to: date
    summary: str
    new: list[WeeklyAnalyticsItemPayload]
    trending_up: list[WeeklyAnalyticsItemPayload]
    trending_down: list[WeeklyAnalyticsItemPayload]
    methodology_version: str | None = None
    taxonomy_version: str | None = None
    snapshot_id: str | None = None
    revision: int | None = None
    generated_at: datetime | None = None
    data_cutoff: datetime | None = None
    status: Literal["ready", "provisional", "insufficient_data", "legacy"] = "legacy"
    narrative_mode: Literal["deepseek", "template", "mixed"] = "template"
    quality: dict = Field(default_factory=dict)
    section_status: dict = Field(default_factory=dict)
    other_signals: list[WeeklyAnalyticsItemPayload] = Field(default_factory=list)


class WeeklyAnalyticsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_date: date
    date_from: date
    date_to: date
    summary: str = Field(min_length=1, max_length=4000)
    new: list[NewsDigestItemPayload] = Field(default_factory=list)
    trending_up: list[NewsDigestItemPayload] = Field(default_factory=list)
    trending_down: list[NewsDigestItemPayload] = Field(default_factory=list)


class WeeklyAnalyticsReportListItem(BaseModel):
    report_date: date
    date_from: date
    date_to: date
    summary: str
    created_at: datetime


class WeeklyAnalyticsReportListResponse(BaseModel):
    items: list[WeeklyAnalyticsReportListItem]


class WeeklyAnalyticsFreshnessResponse(BaseModel):
    report_date: date
    date_from: date
    date_to: date
    article_count: int
    latest_fetch_run_id: str | None = None
    latest_fetch_status: str | None = None
    latest_fetch_started_at: datetime | None = None
    latest_fetch_finished_at: datetime | None = None
    latest_fetch_fetched: int = 0
    latest_fetch_new: int = 0
    latest_fetch_duplicates: int = 0
    latest_fetch_errors: int = 0


class NewsDailyStatsItem(BaseModel):
    stat_date: date
    published_count: int
    discovered_count: int
    fetch_run_count: int
    fetched_count: int
    new_count: int
    duplicate_count: int
    error_count: int


class NewsDailyStatsResponse(BaseModel):
    date_from: date
    date_to: date
    items: list[NewsDailyStatsItem]


class SourceOnboardingCandidateView(BaseModel):
    candidate_id: int
    batch_id: int | None = None
    status: str
    validation_status: str
    candidate_type: str
    normalized_url: str
    raw_input: str | None = None
    review_note: str | None = None
    duplicate_of_candidate_id: int | None = None
    approved_source_id: int | None = None
    validation_detected_type: str | None = None
    validation_error: str | None = None
    validation_details: str | None = None
    validated_at: datetime | None = None


class SourceOnboardingCandidateFilters(BaseModel):
    batch_id: int | None = None
    status: str | None = None
    validation_status: str | None = None


class SourceOnboardingBatchSummary(BaseModel):
    batch_id: int | None = None
    parsed_count: int | None = None
    accepted_count: int | None = None
    rejected_count: int | None = None
    pending_review_count: int = 0
    validated_count: int = 0
    approved_count: int = 0
    rejected_review_count: int = 0
    duplicate_count: int = 0
    total_candidates: int | None = None
    draft_count: int | None = None


class SourceOnboardingCandidateListResponse(BaseModel):
    items: list[SourceOnboardingCandidateView]
    summary: SourceOnboardingBatchSummary
    filters: SourceOnboardingCandidateFilters


class SourceOnboardingRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = None


class SourceOnboardingDuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duplicate_of_candidate_id: int = Field(ge=1)
    reason: str | None = None


class SourceOnboardingEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    normalized_url: str | None = None
    candidate_type: str | None = None
    raw_input: str | None = None
    review_note: str | None = None


class SourceOnboardingApproveResponse(BaseModel):
    candidate_id: int
    status: str
    validation_status: str
    managed_source_created: bool
    approved_source_id: int | None = None
    review_note: str | None = None


class SourceOnboardingRejectResponse(BaseModel):
    candidate_id: int
    status: str
    review_note: str | None = None


class SourceOnboardingDisableResponse(BaseModel):
    candidate_id: int
    status: str
    approved_source_id: int


class SourceOnboardingDuplicateResponse(BaseModel):
    candidate_id: int
    status: str
    duplicate_of_candidate_id: int
    review_note: str | None = None


class SourceOnboardingEditResponse(BaseModel):
    candidate_id: int
    status: str
    normalized_url: str
    candidate_type: str
    raw_input: str
    review_note: str | None = None


class DailySignalLink(BaseModel):
    title: str
    url: str
    publisher: str


class DailySignalEntityItem(BaseModel):
    entity_id: int
    name: str
    type: str
    vendor: str | None = None
    level: Literal["confirmed", "early"]
    variant_of: str | None = None
    variants: list[str] = Field(default_factory=list)
    novelty_quote: str | None = None
    one_liner: str | None = None
    one_liner_source: Literal["summary", "quote"] | None = None
    articles: int
    publishers: int
    links: list[DailySignalLink] = Field(default_factory=list)


class DailySignalTrendItem(BaseModel):
    entity_id: int
    name: str
    type: str
    vendor: str | None = None
    current_7d: int | None = None
    previous_7d: int | None = None
    expected_7d: float | None = None
    today: int
    trailing_mean: float | None = None
    spike: bool = False
    publishers: int
    reason: str | None = None
    links: list[DailySignalLink] = Field(default_factory=list)


class DailySignalStory(BaseModel):
    label: str
    event_type: str
    articles: int
    publishers: int
    entities: list[str] = Field(default_factory=list)
    spikes: list[str] = Field(default_factory=list)
    links: list[DailySignalLink] = Field(default_factory=list)


class DailySignalBriefSentence(BaseModel):
    text: str
    links: list[DailySignalLink] = Field(default_factory=list)
    quote: str | None = None


class DailySignalBrief(BaseModel):
    sentences: list[DailySignalBriefSentence] = Field(default_factory=list)
    model: str | None = None
    brief_version: str | None = None
    generated_at: datetime | None = None


class DailySignalEventCount(BaseModel):
    event_type: str
    label: str
    stories: int
    articles: int
    links: list[DailySignalLink] = Field(default_factory=list)


class DailySignalSectionState(BaseModel):
    state: Literal["ready", "building", "empty", "spikes_only", "hidden"]
    note: str | None = None


class DailySignalCoverage(BaseModel):
    items: int = 0
    matched: int = 0
    extracted: int = 0
    failed: int = 0
    skipped: int = 0
    pending: int = 0
    unmatched: int = 0


class DailySignalsResponse(BaseModel):
    report_date: date
    status: Literal["ready", "partial", "building_history", "unavailable"]
    methodology_version: str | None = None
    extraction_version: str | None = None
    generated_at: datetime | None = None
    novelty_history_days: int = 0
    comparable_complete_days: int = 0
    coverage: DailySignalCoverage = Field(default_factory=DailySignalCoverage)
    notes: list[str] = Field(default_factory=list)
    sections: dict[str, DailySignalSectionState] = Field(default_factory=dict)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    new: list[DailySignalEntityItem] = Field(default_factory=list)
    top_stories: list[DailySignalStory] = Field(default_factory=list)
    rising: list[DailySignalTrendItem] = Field(default_factory=list)
    cooling: list[DailySignalTrendItem] = Field(default_factory=list)
    event_counts: list[DailySignalEventCount] = Field(default_factory=list)
    article_event_types: dict[str, str] = Field(default_factory=dict)
    quiet: bool = False
    brief: DailySignalBrief | None = None


class PeriodSignalsResponse(BaseModel):
    """Stored weekly/monthly signals (017). Nested sections are passed through as stored."""
    period_kind: Literal["week", "month"]
    period_start: date | None = None
    period_end: date | None = None
    status: Literal["ready", "partial", "building_history", "unavailable"]
    methodology_version: str | None = None
    daily_methodology_version: str | None = None
    extraction_version: str | None = None
    generated_at: datetime | None = None
    thresholds: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    quiet: bool = False
    comparison: dict[str, Any] = Field(default_factory=dict)
    sections: dict[str, str] = Field(default_factory=dict)
    top_stories: list[dict[str, Any]] = Field(default_factory=list)
    top_entities: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    new: list[dict[str, Any]] = Field(default_factory=list)
    rising: list[dict[str, Any]] = Field(default_factory=list)
    cooling: list[dict[str, Any]] = Field(default_factory=list)
    trend_source: str | None = None
    event_mix: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    brief: DailySignalBrief | None = None  # the stored `ok` brief; null when missing


class PeriodSignalsIndexItem(BaseModel):
    period_kind: Literal["week", "month"]
    period_start: date
    period_end: date
    status: Literal["ready", "partial", "building_history", "unavailable"]
    computed_at: datetime


class PeriodSignalsIndexResponse(BaseModel):
    periods: list[PeriodSignalsIndexItem] = Field(default_factory=list)
