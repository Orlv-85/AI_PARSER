from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator, model_validator


class HtmlOptions(BaseModel):
    list_selector: str | None = None
    link_selector: str | None = None
    article_selector: str | None = None
    extraction_strategy: str | None = None


class ParserOptions(BaseModel):
    list_mode: str | None = None
    article_mode: str | None = None
    respect_robots: bool | None = None


class SourceDefaults(BaseModel):
    language: str = "en"
    enabled: bool = True
    fetch_interval_minutes: int = Field(default=60, ge=1)
    respect_robots: bool = True
    source_weight: float = Field(default=1.0, ge=0.0)


class SourceConfig(BaseModel):
    id: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    type: Literal["rss", "html"]
    url: HttpUrl
    language: str = "en"
    enabled: bool = True
    fetch_interval_minutes: int = Field(default=30, ge=1)
    respect_robots: bool = True
    source_weight: float = Field(default=1.0, ge=0.0)
    html: HtmlOptions | None = None
    parser_options: ParserOptions | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
        lowered = value.lower()
        if any(char not in allowed for char in lowered):
            raise ValueError("id must contain only a-z, 0-9, '_' or '-'")
        return lowered

    @model_validator(mode="after")
    def validate_html_options(self) -> SourceConfig:
        if self.type == "html" and self.html is None and self.parser_options is None:
            raise ValueError("html source requires 'html' or 'parser_options'")
        return self


class SourcesFile(BaseModel):
    version: int | None = None
    defaults: SourceDefaults | None = None
    sources: list[SourceConfig]


def load_sources(path: Path) -> list[SourceConfig]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []

    payload: dict[str, Any]
    if isinstance(raw, list):
        payload = {"sources": raw}
    elif isinstance(raw, dict):
        defaults = SourceDefaults.model_validate(raw.get("defaults", {}))
        merged_sources: list[dict[str, Any]] = []
        for source in raw.get("sources", []):
            merged: dict[str, Any] = {
                "language": defaults.language,
                "enabled": defaults.enabled,
                "fetch_interval_minutes": defaults.fetch_interval_minutes,
                "respect_robots": defaults.respect_robots,
                "source_weight": defaults.source_weight,
            }
            merged.update(source)
            merged_sources.append(merged)
        payload = {"version": raw.get("version"), "defaults": defaults, "sources": merged_sources}
    else:
        raise ValueError("sources.yaml must contain either a list or a mapping with 'sources'")

    try:
        parsed = SourcesFile.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid sources configuration: {exc}") from exc

    return parsed.sources
