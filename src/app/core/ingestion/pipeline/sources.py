"""Source config and fetch-state helpers."""
from datetime import UTC, datetime
from typing import Any, cast

from app.config.sources import SourceConfig
from app.core.ingestion.pipeline.models import FetchResult
from app.ingest.page_filter import (
    MANAGED_LINK_SELECTORS,
)
from app.storage.source_repo import SourceRepo


def _managed_source_to_config(source: object) -> SourceConfig:
    source_model = cast(Any, source)
    source_type = str(source_model.type).lower()
    payload: dict[str, object] = {
        "id": str(source_model.source_key),
        "name": str(source_model.name),
        "type": source_type,
        "url": str(source_model.url),
        "enabled": bool(source_model.enabled),
        "fetch_interval_minutes": int(source_model.fetch_interval_minutes),
        "source_weight": float(source_model.source_weight),
    }
    if source_type == "html":
        selector = MANAGED_LINK_SELECTORS.get(str(source_model.url).rstrip("/"))
        payload["html"] = {"link_selector": selector} if selector else {}
    return SourceConfig.model_validate(payload)


def _clear_source_validators(source_repo: SourceRepo, db_source_id: int) -> None:
    source_repo.update_fetch_state(
        source_id=db_source_id,
        etag=None,
        last_modified=None,
        last_status_code=None,
        last_checked_at=datetime.now(UTC),
    )


def _persist_fetch_state_if_present(
    *,
    source_repo: SourceRepo,
    db_source_id: int,
    result: FetchResult,
) -> None:
    has_metadata = any(
        value is not None for value in (result.etag, result.last_modified, result.status_code)
    ) or result.not_modified
    if not has_metadata:
        return
    source_repo.update_fetch_state(
        source_id=db_source_id,
        etag=result.etag,
        last_modified=result.last_modified,
        last_status_code=result.status_code,
        last_checked_at=datetime.now(UTC),
    )
