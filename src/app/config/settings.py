from functools import lru_cache
from pathlib import Path

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
    per_source_min_interval_seconds: float = 1.0
    respect_robots_txt: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
