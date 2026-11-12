"""Per-source metrics logging and dispatch of a fetched result."""
from logging import Logger

from app.ingest.html import (
    HtmlListPageResult,
)
from app.storage.source_repo import SourceRepo
from app.usecases.ingestion.pipeline.html_links import _process_html_links_two_stage
from app.usecases.ingestion.pipeline.models import FetchResult, SourceMetrics, SourceRun
from app.usecases.ingestion.pipeline.rss import _process_fetched_source_items
from app.usecases.ingestion.pipeline.sources import _persist_fetch_state_if_present


def _log_source_metrics(
    *,
    logger: Logger,
    run_id: str,
    metrics: SourceMetrics,
    enabled: bool,
) -> None:
    if not enabled:
        return
    logger.info(
        "source_fetch_finished",
        {
            "run_id": run_id,
            "source_id": metrics.source_id,
            "source_type": metrics.source_type,
            "fetched_items": metrics.fetched_items,
            "examined_items": metrics.examined_items,
            "new_items": metrics.new_items,
            "duplicate_items": metrics.duplicate_items,
            "skipped_known_items": metrics.skipped_known_items,
            "early_stop_hit": metrics.early_stop_hit,
            "not_modified": metrics.not_modified,
            "errors": metrics.errors,
            "replay_items": metrics.replay_items,
            "semantic_rejected": metrics.semantic_rejected,
            "semantic_unresolved": metrics.semantic_unresolved,
            "semantic_cache_hits": metrics.semantic_cache_hits,
            "screening_paused": metrics.screening_paused,
        },
    )


def _process_source_result(
    run: SourceRun, fetch_result: FetchResult, *, source_repo: SourceRepo, metrics: SourceMetrics,
) -> None:
    admission_state = run.admission_state
    _persist_fetch_state_if_present(
        source_repo=source_repo,
        db_source_id=run.db_source_id,
        result=fetch_result,
    )
    if fetch_result.not_modified:
        metrics.not_modified = True
        return

    if isinstance(fetch_result, HtmlListPageResult):
        quality_flags: list[str] = []
        (
            metrics.fetched_items,
            metrics.new_items,
            metrics.duplicate_items,
            metrics.skipped_known_items,
            metrics.early_stop_hit,
        ) = _process_html_links_two_stage(run, fetch_result.links, quality_flags)
        metrics.examined_items = metrics.fetched_items
        metrics.acquisition_stopped = bool(admission_state and admission_state.paused)
        metrics.coverage_complete = not quality_flags
        return

    items = fetch_result
    metrics.coverage_complete = fetch_result.coverage_complete and not any(
        item.published_at is None or item.publication_date_kind != "published" for item in items
    )
    metrics.fetched_items = len(items)
    (
        metrics.new_items,
        metrics.duplicate_items,
        metrics.skipped_known_items,
        metrics.early_stop_hit,
    ) = _process_fetched_source_items(run, items, metrics)
