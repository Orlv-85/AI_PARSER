from datetime import date, datetime
from typing import Literal

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


class NewsItem(BaseModel):
    title: str
    published_at: datetime
    rank_score: float
    url_canonical: str
    source_id: int | None = None
    source_key: str | None = None
    source_name: str | None = None


class NewsArticleDetail(BaseModel):
    article_id: int
    title: str
    summary: str | None = None
    content: str | None = None
    published_at: datetime
    rank_score: float
    url: str
    url_canonical: str
    source_id: int | None = None
    source_key: str | None = None
    source_name: str | None = None


class DigestLinkFeedItem(BaseModel):
    article_id: int
    title: str
    published_at: datetime
    url: str
    url_canonical: str
    source_id: int | None = None
    source_key: str | None = None
    source_name: str | None = None


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
