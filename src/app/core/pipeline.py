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
from app.ingest.rss import fetch_rss
from app.storage import SessionLocal, create_all
from app.storage.repos import ArticleRepo, SourceRepo


@dataclass(frozen=True)
class FetchSummary:
    run_id: str
    fetched: int
    new: int
    duplicates: int
    errors: int


def _fetch_source_items(
    *,
    config: SourceConfig,
    settings: Settings,
    logger: Logger,
    run_id: str,
    full_text_semaphore: BoundedSemaphore | None,
):  # type: ignore[no-untyped-def]
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
        return fetch_rss(
            config.id,
            str(config.url),
            settings.request_timeout_seconds,
            fetcher=fetcher,
            extract_full_text=settings.rss_extract_full_text,
            full_text_max_items=settings.rss_full_text_max_items_per_source,
            full_text_semaphore=full_text_semaphore,
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
    enabled_sources: list[tuple[int, SourceConfig, int]],
    settings: Settings,
    logger: Logger,
    run_id: str,
    full_text_semaphore: BoundedSemaphore | None,
) -> tuple[dict[int, list], int]:
    fetched_by_index: dict[int, list] = {}
    error_count = 0
    if not enabled_sources:
        return fetched_by_index, error_count

    max_workers = max(1, min(settings.concurrency_limit, len(enabled_sources)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures: dict[Future, tuple[int, SourceConfig, int]] = {
            pool.submit(
                _fetch_source_items,
                config=config,
                settings=settings,
                logger=logger,
                run_id=run_id,
                full_text_semaphore=full_text_semaphore,
            ): (idx, config, db_source_id)
            for idx, config, db_source_id in enabled_sources
        }
        for future in as_completed(futures):
            idx, config, _db_source_id = futures[future]
            try:
                fetched_by_index[idx] = future.result()
            except Exception as exc:
                error_count += 1
                _log_source_fetch_error(logger=logger, run_id=run_id, config=config, exc=exc)
    return fetched_by_index, error_count


def _process_fetched_source_items(
    *,
    items: list,
    config: SourceConfig,
    db_source_id: int,
    article_repo: ArticleRepo,
    settings: Settings,
) -> tuple[int, int]:
    new_count = 0
    duplicate_count = 0
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
            rss_known_streak += 1
            if rss_known_streak >= rss_known_streak_stop:
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

    return new_count, duplicate_count


def run_fetch_cycle(*, settings: Settings, logger: Logger) -> FetchSummary:
    configs = load_sources(settings.sources_path)
    create_all()

    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    fetched_count = 0
    new_count = 0
    duplicate_count = 0
    error_count = 0
    full_text_semaphore = (
        BoundedSemaphore(settings.rss_full_text_concurrency_limit)
        if settings.rss_full_text_concurrency_limit
        and settings.rss_full_text_concurrency_limit > 0
        else None
    )
    with SessionLocal() as session:
        source_repo = SourceRepo(session)
        article_repo = ArticleRepo(session)
        enabled_sources: list[tuple[int, SourceConfig, int]] = []

        for idx, config in enumerate(configs):
            db_source = source_repo.upsert_source(config)
            if not config.enabled:
                continue
            enabled_sources.append((idx, config, db_source.id))

        fetched_by_index, fetch_errors = _collect_fetched_items(
            enabled_sources=enabled_sources,
            settings=settings,
            logger=logger,
            run_id=run_id,
            full_text_semaphore=full_text_semaphore,
        )
        error_count += fetch_errors

        for idx, config, db_source_id in enabled_sources:
            items = fetched_by_index.get(idx)
            if items is None:
                continue

            fetched_count += len(items)
            source_new, source_duplicates = _process_fetched_source_items(
                items=items,
                config=config,
                db_source_id=db_source_id,
                article_repo=article_repo,
                settings=settings,
            )
            new_count += source_new
            duplicate_count += source_duplicates

        session.commit()

    logger.info(
        "fetch_run_finished",
        {
            "run_id": run_id,
            "fetched": fetched_count,
            "new": new_count,
            "duplicates": duplicate_count,
            "errors": error_count,
        },
    )
    return FetchSummary(
        run_id=run_id,
        fetched=fetched_count,
        new=new_count,
        duplicates=duplicate_count,
        errors=error_count,
    )
