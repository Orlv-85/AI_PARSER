from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from logging import Logger
from threading import BoundedSemaphore

from app.config.settings import Settings
from app.config.sources import SourceConfig, load_sources
from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.scoring import ai_relevance_score, freshness_score, rank_score
from app.ingest.fetcher import Fetcher
from app.ingest.html import fetch_html
from app.ingest.rss import fetch_rss, fetch_rss_with_metadata
from app.storage import SessionLocal, create_all
from app.storage.repos import ArticleRepo, SourceRepo

_DEFAULT_FETCH_RSS_WITH_METADATA = fetch_rss_with_metadata


@dataclass(frozen=True)
class FetchSummary:  # pylint: disable=too-many-instance-attributes
    run_id: str
    fetched: int
    new: int
    duplicates: int
    errors: int
    not_modified_sources: int = 0
    skipped_known_html_links: int = 0
    early_stop_hits: int = 0


@dataclass
class SourceMetrics:  # pylint: disable=too-many-instance-attributes
    source_id: str
    source_type: str
    fetched_items: int = 0
    new_items: int = 0
    duplicate_items: int = 0
    errors: int = 0
    skipped_known_items: int = 0
    early_stop_hit: bool = False
    not_modified: bool = False


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
            "new_items": metrics.new_items,
            "duplicate_items": metrics.duplicate_items,
            "skipped_known_items": metrics.skipped_known_items,
            "early_stop_hit": metrics.early_stop_hit,
            "not_modified": metrics.not_modified,
            "errors": metrics.errors,
        },
    )


def _fetch_source_items(
    *,
    config: SourceConfig,
    db_source_id: int,
    fetch_state: dict[str, object | None] | None,
    enable_rss_fetch_state: bool,
    settings: Settings,
    logger: Logger,
    run_id: str,
    full_text_semaphore: BoundedSemaphore | None,
):  # type: ignore[no-untyped-def]
    del db_source_id
    fetcher = Fetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        per_source_min_interval_seconds=settings.per_source_min_interval_seconds,
    )
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
        if_none_match = None
        if_modified_since = None
        if enable_rss_fetch_state and fetch_state is not None:
            etag = fetch_state.get("etag")
            last_modified = fetch_state.get("last_modified")
            if_none_match = etag if isinstance(etag, str) else None
            if_modified_since = last_modified if isinstance(last_modified, str) else None
        use_explicit_metadata_fetch = (
            enable_rss_fetch_state
            and fetch_rss_with_metadata is not _DEFAULT_FETCH_RSS_WITH_METADATA
        )
        if use_explicit_metadata_fetch:
            return fetch_rss_with_metadata(
                config.id,
                str(config.url),
                settings.request_timeout_seconds,
                fetcher=fetcher,
                if_none_match=if_none_match,
                if_modified_since=if_modified_since,
            )
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
    return fetch_html(
        config,
        settings.request_timeout_seconds,
        fetcher=fetcher,
    )


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


def _collect_fetched_items(
    *,
    enabled_sources: list[tuple[int, SourceConfig, int, dict[str, object | None] | None, bool]],
    settings: Settings,
    logger: Logger,
    run_id: str,
    full_text_semaphore: BoundedSemaphore | None,
) -> tuple[dict[int, object], int]:
    fetched_by_index: dict[int, object] = {}
    error_count = 0
    if not enabled_sources:
        return fetched_by_index, error_count

    max_workers = max(1, min(settings.concurrency_limit, len(enabled_sources)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures: dict[Future, tuple[int, SourceConfig, int]] = {
            pool.submit(
                _fetch_source_items,
                config=config,
                db_source_id=db_source_id,
                fetch_state=fetch_state,
                enable_rss_fetch_state=enable_rss_fetch_state,
                settings=settings,
                logger=logger,
                run_id=run_id,
                full_text_semaphore=full_text_semaphore,
            ): (idx, config, db_source_id)
            for idx, config, db_source_id, fetch_state, enable_rss_fetch_state in enabled_sources
        }
        for future in as_completed(futures):
            idx, config, _db_source_id = futures[future]
            try:
                fetched_by_index[idx] = future.result()
            except Exception as exc:
                error_count += 1
                _log_source_fetch_error(logger=logger, run_id=run_id, config=config, exc=exc)
    return fetched_by_index, error_count


def _source_repo_get_fetch_state(
    source_repo: SourceRepo,
    *,
    source_id: int,
) -> tuple[dict[str, object | None] | None, bool]:
    getter = getattr(source_repo, "get_fetch_state", None)
    if callable(getter):
        return getter(source_id=source_id), True
    getter = getattr(source_repo, "get_source_fetch_state", None)
    if callable(getter):
        return getter(source_id), True
    return None, False


def _source_repo_update_fetch_state(
    source_repo: SourceRepo,
    *,
    source_id: int,
    etag: str | None,
    last_modified: str | None,
    last_status_code: int | None,
    last_checked_at: datetime,
) -> bool:
    updater = getattr(source_repo, "update_fetch_state", None)
    if callable(updater):
        updater(
            source_id=source_id,
            etag=etag,
            last_modified=last_modified,
            last_status_code=last_status_code,
            last_checked_at=last_checked_at,
        )
        return True
    updater = getattr(source_repo, "update_source_fetch_state", None)
    if callable(updater):
        updater(
            source_id,
            etag=etag,
            last_modified=last_modified,
            last_status_code=last_status_code,
            last_checked_at=last_checked_at,
        )
        return True
    return False


def _fetch_result_items(result: object) -> list:
    items = getattr(result, "items", None)
    if isinstance(items, list):
        return items
    if isinstance(result, list):
        return result
    return []


def _persist_rss_fetch_state_if_present(
    *,
    source_repo: SourceRepo,
    db_source_id: int,
    result: object,
) -> None:
    etag = getattr(result, "etag", None)
    last_modified = getattr(result, "last_modified", None)
    status_code = getattr(result, "status_code", None)
    has_metadata = any(
        value is not None for value in (etag, last_modified, status_code)
    ) or hasattr(result, "not_modified")
    if not has_metadata:
        return
    _source_repo_update_fetch_state(
        source_repo,
        source_id=db_source_id,
        etag=etag if isinstance(etag, str) else None,
        last_modified=last_modified if isinstance(last_modified, str) else None,
        last_status_code=int(status_code) if status_code is not None else None,
        last_checked_at=datetime.now(UTC),
    )


def _process_fetched_source_items(
    *,
    items: list,
    config: SourceConfig,
    db_source_id: int,
    article_repo: ArticleRepo,
    settings: Settings,
) -> tuple[int, int, int, bool]:
    new_count = 0
    duplicate_count = 0
    skipped_known_items = 0
    early_stop_hit = False
    rss_known_streak = 0
    rss_known_streak_stop = int(getattr(settings, "rss_known_streak_stop", 0) or 0)
    exists_by_canonical_hash = getattr(article_repo, "exists_by_canonical_hash", None)
    exists_by_canonical_hash_fn = (
        exists_by_canonical_hash if callable(exists_by_canonical_hash) else None
    )
    use_rss_early_stop = (
        config.type == "rss"
        and rss_known_streak_stop > 0
        and exists_by_canonical_hash_fn is not None
    )

    for item in items:
        canonical = canonicalize_url(str(item.url))
        canonical_hash = canonical_url_hash(str(item.url))
        if (
            use_rss_early_stop
            and exists_by_canonical_hash_fn is not None
            and exists_by_canonical_hash_fn(canonical_hash)
        ):
            duplicate_count += 1
            skipped_known_items += 1
            rss_known_streak += 1
            if rss_known_streak >= rss_known_streak_stop:
                early_stop_hit = True
                break
            continue

        if use_rss_early_stop:
            rss_known_streak = 0

        relevance = ai_relevance_score(item)
        freshness = freshness_score(item.published_at)
        rank = rank_score(
            relevance=relevance,
            freshness=freshness,
            source_weight=config.source_weight,
        )
        _, is_new = article_repo.insert_article(
            source_id=db_source_id,
            title=item.title,
            url=str(item.url),
            url_canonical=canonical,
            url_canonical_hash=canonical_hash,
            published_at=item.published_at or datetime.now(UTC),
            summary=item.summary,
            content=item.content,
            ai_relevance_score=relevance,
            freshness_score=freshness,
            rank_score=rank,
        )
        if is_new:
            new_count += 1
        else:
            duplicate_count += 1

    return new_count, duplicate_count, skipped_known_items, early_stop_hit


# pylint: disable=too-many-statements
def run_fetch_cycle(*, settings: Settings, logger: Logger) -> FetchSummary:
    configs = load_sources(settings.sources_path)
    create_all()

    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    fetched_count = 0
    new_count = 0
    duplicate_count = 0
    error_count = 0
    optimization_not_modified_sources = 0
    optimization_skipped_known_html_links = 0
    optimization_early_stop_hits = 0
    full_text_semaphore = (
        BoundedSemaphore(settings.rss_full_text_concurrency_limit)
        if settings.rss_full_text_concurrency_limit
        and settings.rss_full_text_concurrency_limit > 0
        else None
    )
    with SessionLocal() as session:
        source_repo = SourceRepo(session)
        article_repo = ArticleRepo(session)
        enabled_sources: list[
            tuple[int, SourceConfig, int, dict[str, object | None] | None, bool]
        ] = []

        for idx, config in enumerate(configs):
            db_source = source_repo.upsert_source(config)
            if not config.enabled:
                continue
            fetch_state, supports_fetch_state = _source_repo_get_fetch_state(
                source_repo,
                source_id=db_source.id,
            )
            enabled_sources.append(
                (
                    idx,
                    config,
                    db_source.id,
                    fetch_state,
                    bool(supports_fetch_state and config.type == "rss"),
                )
            )

        fetched_by_index, fetch_errors = _collect_fetched_items(
            enabled_sources=enabled_sources,
            settings=settings,
            logger=logger,
            run_id=run_id,
            full_text_semaphore=full_text_semaphore,
        )
        error_count += fetch_errors

        for idx, config, db_source_id, _fetch_state, _enable_rss_fetch_state in enabled_sources:
            fetch_result = fetched_by_index.get(idx)
            if fetch_result is None:
                continue

            source_metrics = SourceMetrics(source_id=config.id, source_type=config.type)
            if config.type == "rss":
                _persist_rss_fetch_state_if_present(
                    source_repo=source_repo,
                    db_source_id=db_source_id,
                    result=fetch_result,
                )
                if bool(getattr(fetch_result, "not_modified", False)):
                    source_metrics.not_modified = True
                    optimization_not_modified_sources += 1
                    _log_source_metrics(
                        logger=logger,
                        run_id=run_id,
                        metrics=source_metrics,
                        enabled=bool(getattr(settings, "fetch_emit_source_metrics", True)),
                    )
                    continue

            items = _fetch_result_items(fetch_result)
            fetched_count += len(items)
            source_metrics.fetched_items = len(items)
            (
                source_new,
                source_duplicates,
                source_skipped_known,
                source_early_stop,
            ) = _process_fetched_source_items(
                items=items,
                config=config,
                db_source_id=db_source_id,
                article_repo=article_repo,
                settings=settings,
            )
            new_count += source_new
            duplicate_count += source_duplicates
            source_metrics.new_items = source_new
            source_metrics.duplicate_items = source_duplicates
            source_metrics.skipped_known_items = source_skipped_known
            source_metrics.early_stop_hit = source_early_stop
            if source_early_stop:
                optimization_early_stop_hits += 1
            if config.type == "html":
                optimization_skipped_known_html_links += source_skipped_known
            _log_source_metrics(
                logger=logger,
                run_id=run_id,
                metrics=source_metrics,
                enabled=bool(getattr(settings, "fetch_emit_source_metrics", True)),
            )

        session.commit()

    logger.info(
        "fetch_run_finished",
        {
            "run_id": run_id,
            "fetched": fetched_count,
            "new": new_count,
            "duplicates": duplicate_count,
            "errors": error_count,
            "not_modified_sources": optimization_not_modified_sources,
            "skipped_known_html_links": optimization_skipped_known_html_links,
            "early_stop_hits": optimization_early_stop_hits,
        },
    )
    return FetchSummary(
        run_id=run_id,
        fetched=fetched_count,
        new=new_count,
        duplicates=duplicate_count,
        errors=error_count,
        not_modified_sources=optimization_not_modified_sources,
        skipped_known_html_links=optimization_skipped_known_html_links,
        early_stop_hits=optimization_early_stop_hits,
    )
