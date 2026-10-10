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
    respect_robots_txt: bool = True
    auth_enabled: bool = False
    auth_username: str | None = None
    auth_password_hash: str | None = None
    auth_secret: str | None = None
    auth_session_ttl_seconds: int = 3600
    auth_cookie_name: str = "ainews_session"
    auth_cookie_secure: bool = False
    mcp_auth_enabled: bool = False
    mcp_auth_token: str | None = None

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
    def validate_mcp_auth_config(self) -> Settings:
        if not self.mcp_auth_enabled:
            return self
        if not self.mcp_auth_token or not self.mcp_auth_token.strip():
            raise ValueError(
                "mcp auth is enabled, missing required mcp auth settings: "
                "AINEWS_MCP_AUTH_TOKEN"
            )
        if len(self.mcp_auth_token.strip()) < 16:
            raise ValueError("AINEWS_MCP_AUTH_TOKEN must be at least 16 characters long")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
