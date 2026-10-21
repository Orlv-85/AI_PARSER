from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AINEWS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/ai_news.db"
    sources_path: Path = Path("sources.yaml")
    request_timeout_seconds: float = 15.0
    max_retries: int = 3
    concurrency_limit: int = 8
    fetch_execution_profile: str = "balanced"
    fetch_rss_concurrency_limit: int | None = None
    fetch_html_concurrency_limit: int | None = None
    html_link_parser: str = "auto"
    per_source_min_interval_seconds: float = 1.0
    fetch_http_max_connections: int | None = 20
    fetch_http_max_keepalive_connections: int | None = 10
    fetch_emit_source_metrics: bool = True
    fetch_conditional_rss_enabled: bool = True
    fetch_conditional_html_list_enabled: bool = False
    rss_extract_full_text: bool = False
    rss_full_text_max_items_per_source: int = 20
    rss_full_text_concurrency_limit: int | None = None
    rss_known_streak_stop: int = 20
    html_known_streak_stop: int = 20
    html_max_links_per_source: int | None = 50
    article_batch_upsert_enabled: bool = False
    jev_enabled: bool = False
    jev_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("JEV_API_KEY", "AINEWS_JEV_API_KEY", "jev_api_key"),
    )
    jev_model: str = "jev-1.13.0"
    jev_timeout_seconds: float = Field(default=3.0, gt=0, allow_inf_nan=False)
    jev_category_min_confidence: float = Field(
        default=0.7, ge=0, le=1, allow_inf_nan=False,
    )
    semantic_admission_enabled: bool = False
    semantic_admission_policy_version: str = "semantic-admission-2026-10-10"
    semantic_admission_prompt_version: str = "semantic-admission-prompt-1"
    daily_enrichment_enabled: bool = False
    ds_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("DS_API_KEY", "AINEWS_DS_API_KEY"),
    )
    source_review_deepseek_model: str = "deepseek-flash"
    weekly_v2_enabled: bool = False
    weekly_jev_model: str = "jev-1.13.0"
    weekly_deepseek_model: str = "deepseek-flash"
    weekly_prompt_version: str = "weekly-1"
    weekly_provider_concurrency: int = Field(default=4, ge=1, le=4)
    weekly_deepseek_timeout_seconds: float = Field(default=60, gt=0, le=60)
    weekly_jev_decision_budget: int = Field(default=1000, ge=0, le=1000)
    weekly_ambiguity_budget: int = Field(default=100, ge=0, le=100)
    weekly_narrative_budget: int = Field(default=16, ge=0, le=16)
    weekly_wall_seconds: int = Field(default=900, ge=1, le=900)
    weekly_input_token_cap: int = Field(default=16000, ge=100, le=16000)
    weekly_output_token_cap: int = Field(default=1200, ge=100, le=4000)
    weekly_narrative_prompt_version: str = "weekly-narrative-5"
    weekly_narrative_input_byte_cap: int = Field(default=16000, ge=2000, le=32000)
    weekly_narrative_output_token_cap: int = Field(default=2400, ge=100, le=4096)
    weekly_input_safety_cap: int = Field(default=100000, ge=1)
    weekly_publisher_overrides: dict[str, str] = Field(default_factory=dict)
    daily_signals_enabled: bool = False
    daily_signals_comparable_from: date = date(2026, 10, 10)
    daily_signals_max_calls: int = Field(default=200, ge=1, le=5000)
    daily_signals_max_seconds: int = Field(default=2700, ge=60, le=14400)
    daily_signals_max_usd: str = "0.50"
    daily_signals_brief_model: str = "deepseek-v4-pro"
    respect_robots_txt: bool = True
    auth_enabled: bool = False
    auth_username: str | None = None
    auth_password_hash: str | None = None
    auth_secret: str | None = None
    auth_session_ttl_seconds: int = 3600
    auth_cookie_name: str = "ainews_session"
    auth_cookie_secure: bool = False
    publish_api_token: str | None = Field(default=None, repr=False)

    @property
    def is_auth_enabled(self) -> bool:
        return self.auth_enabled or bool(
            self.auth_username and self.auth_password_hash and self.auth_secret
        )

    @model_validator(mode="after")
    def validate_auth_config(self) -> Settings:
        has_any_auth_value = bool(self.auth_username or self.auth_password_hash or self.auth_secret)
        if self.auth_enabled or has_any_auth_value:
            missing: list[str] = []
            if not self.auth_username:
                missing.append("AINEWS_AUTH_USERNAME")
            if not self.auth_password_hash:
                missing.append("AINEWS_AUTH_PASSWORD_HASH")
            if not self.auth_secret:
                missing.append("AINEWS_AUTH_SECRET")

            if missing:
                fields = ", ".join(missing)
                raise ValueError(
                    f"Authentication is enabled, missing required auth settings: {fields}"
                )

            if self.auth_secret and len(self.auth_secret) < 32:
                raise ValueError("AINEWS_AUTH_SECRET must be at least 32 characters long")

            if self.auth_session_ttl_seconds <= 0:
                raise ValueError("AINEWS_AUTH_SESSION_TTL_SECONDS must be greater than 0")

        return self

    @model_validator(mode="after")
    def validate_daily_signals_usd(self) -> Settings:
        try:
            amount = Decimal(self.daily_signals_max_usd)
        except InvalidOperation as error:
            raise ValueError("AINEWS_DAILY_SIGNALS_MAX_USD must be a dollar amount") from error
        if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.000001")):
            raise ValueError("AINEWS_DAILY_SIGNALS_MAX_USD must be a dollar amount")
        return self

    @model_validator(mode="after")
    def validate_publish_api_token(self) -> Settings:
        # Bearer token for machine publishers of digests and weekly reports.
        token = (self.publish_api_token or "").strip()
        if not token:
            self.publish_api_token = None
            return self
        if len(token) < 32:
            raise ValueError("AINEWS_PUBLISH_API_TOKEN must be at least 32 characters long")
        self.publish_api_token = token
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
