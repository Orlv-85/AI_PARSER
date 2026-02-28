from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
