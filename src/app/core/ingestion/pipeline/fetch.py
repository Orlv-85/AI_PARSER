"""Network fetch of enabled sources: conditional validators, groups, worker pool."""
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from logging import Logger
from threading import BoundedSemaphore

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.ingestion.pipeline.models import EnabledSource, FetchResult
from app.ingest.fetcher import Fetcher
from app.ingest.html import (
    HtmlListPageResult,
    fetch_html_links,
    fetch_html_links_with_metadata,
)
from app.ingest.rss import fetch_rss


def _stored_validators(fetch_state: dict[str, object | None]) -> tuple[str | None, str | None]:
    etag = fetch_state.get("etag")
    last_modified = fetch_state.get("last_modified")
    return (
        etag if isinstance(etag, str) else None,
        last_modified if isinstance(last_modified, str) else None,
    )


def _fetch_source_items(
    *,
    config: SourceConfig,
    db_source_id: int,
    fetch_state: dict[str, object | None],
    settings: Settings,
    logger: Logger,
    run_id: str,
    full_text_semaphore: BoundedSemaphore | None,
) -> FetchResult:
    del db_source_id
    conditional = (
        settings.fetch_conditional_rss_enabled if config.type == "rss"
        else settings.fetch_conditional_html_list_enabled
    )
    if_none_match, if_modified_since = (
        _stored_validators(fetch_state) if conditional else (None, None))
    fetcher = Fetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        per_source_min_interval_seconds=settings.per_source_min_interval_seconds,
        http_max_connections=settings.fetch_http_max_connections,
        http_max_keepalive_connections=settings.fetch_http_max_keepalive_connections,
    )
    try:
        logger.info(
            "source_fetch_started",
            {
                "run_id": run_id,
                "source_id": config.id,
                "stage": "fetch",
                "url": str(config.url),
            },
        )
        if config.type == "rss":
            return fetch_rss(
                config.id,
                str(config.url),
                settings.request_timeout_seconds,
                fetcher=fetcher,
                extract_full_text=settings.rss_extract_full_text,
                full_text_max_items=settings.rss_full_text_max_items_per_source,
                full_text_semaphore=full_text_semaphore,
                if_none_match=if_none_match,
                if_modified_since=if_modified_since,
            )
        if conditional:
            return fetch_html_links_with_metadata(
                config,
                settings.request_timeout_seconds,
                fetcher=fetcher,
                link_parser=settings.html_link_parser,
                if_none_match=if_none_match,
                if_modified_since=if_modified_since,
            )
        return HtmlListPageResult(links=fetch_html_links(
            config,
            settings.request_timeout_seconds,
            fetcher=fetcher,
            link_parser=settings.html_link_parser,
        ))
    finally:
        fetcher.close()


def _log_source_fetch_error(
    *,
    logger: Logger,
    run_id: str,
    config: SourceConfig,
    exc: Exception,
) -> None:
    cause = exc.__cause__
    logger.error(
        "source_fetch_failed",
        {
            "run_id": run_id,
            "source_id": config.id,
            "stage": "fetch",
            "url": str(config.url),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "cause_type": type(cause).__name__ if cause is not None else None,
            "cause_message": str(cause) if cause is not None else None,
        },
    )


def _profiled_source_groups(
    enabled_sources: list[EnabledSource], settings: Settings,
) -> list[list[EnabledSource]]:
    profile = settings.fetch_execution_profile
    if profile not in {"rss_fast", "html_heavy"}:
        return [enabled_sources]

    rss_sources = [entry for entry in enabled_sources if entry[1].type == "rss"]
    html_sources = [entry for entry in enabled_sources if entry[1].type == "html"]
    groups = [rss_sources, html_sources] if profile == "rss_fast" else [html_sources, rss_sources]
    return [group for group in groups if group]


def _source_group_max_workers(group: list[EnabledSource], settings: Settings) -> int:
    max_workers: int = max(1, min(settings.concurrency_limit, len(group)))
    if not group:
        return max_workers
    source_type = group[0][1].type
    if any(entry[1].type != source_type for entry in group):
        return max_workers
    type_limit = (
        settings.fetch_rss_concurrency_limit if source_type == "rss"
        else settings.fetch_html_concurrency_limit
    )
    if type_limit is not None and type_limit > 0:
        max_workers = min(max_workers, type_limit)
    return max_workers


def _collect_fetched_items(
    *,
    enabled_sources: list[EnabledSource],
    settings: Settings,
    logger: Logger,
    run_id: str,
    full_text_semaphore: BoundedSemaphore | None,
) -> tuple[dict[int, FetchResult], int]:
    fetched_by_index: dict[int, FetchResult] = {}
    error_count = 0
    if not enabled_sources:
        return fetched_by_index, error_count

    for group in _profiled_source_groups(enabled_sources, settings):
        max_workers = _source_group_max_workers(group, settings)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures: dict[Future, tuple[int, SourceConfig, int]] = {
                pool.submit(
                    _fetch_source_items,
                    config=config,
                    db_source_id=db_source_id,
                    fetch_state=fetch_state,
                    settings=settings,
                    logger=logger,
                    run_id=run_id,
                    full_text_semaphore=full_text_semaphore,
                ): (idx, config, db_source_id)
                for idx, config, db_source_id, fetch_state in group
            }
            for future in as_completed(futures):
                idx, config, _db_source_id = futures[future]
                try:
                    fetched_by_index[idx] = future.result()
                except Exception as exc:
                    error_count += 1
                    _log_source_fetch_error(logger=logger, run_id=run_id, config=config, exc=exc)
    return fetched_by_index, error_count
