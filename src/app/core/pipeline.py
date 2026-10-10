# pylint: disable=too-many-lines
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from logging import Logger
from threading import BoundedSemaphore
from typing import Any, cast

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.config.sources import SourceConfig, load_sources
from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.jev import JevRelevanceScorer, jev_relevance_scorer
from app.core.scoring import ai_relevance_score, freshness_score, rank_score
from app.ingest.fetcher import Fetcher
from app.ingest.html import (
    fetch_html,
    fetch_html_article,
    fetch_html_links,
    fetch_html_links_with_metadata,
)
from app.ingest.page_filter import (
    MANAGED_LINK_SELECTORS,
    log_exclusion,
    text_exclusion_reason,
    url_exclusion_reason,
)
from app.ingest.rss import fetch_rss, fetch_rss_with_metadata
from app.storage import SessionLocal, create_all
from app.storage.repos import ArticleRepo, SourceRepo, WeeklyAnalyticsRepo
from app.storage.weekly import WeeklyStore, record_attempt, record_observation, register_source

_DEFAULT_FETCH_RSS_WITH_METADATA = fetch_rss_with_metadata
_DEFAULT_FETCH_HTML = fetch_html
_DEFAULT_FETCH_HTML_LINKS = fetch_html_links
_DEFAULT_FETCH_HTML_ARTICLE = fetch_html_article


@dataclass(frozen=True)
class FetchSummary:  # pylint: disable=too-many-instance-attributes
    run_id: str
    source_count: int
    fetched: int
    new: int
    duplicates: int
    errors: int
    not_modified_sources: int = 0
    skipped_known_html_links: int = 0
    early_stop_hits: int = 0


@dataclass(frozen=True)
class HtmlLinkFetchResult:
    links: list[str]
    not_modified: bool = False
    status_code: int | None = None
    etag: str | None = None
    last_modified: str | None = None


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
    coverage_complete: bool = True


def _coerce_html_link_fetch_result(result: object) -> HtmlLinkFetchResult:
    status_code = getattr(result, "status_code", None)
    etag = getattr(result, "etag", None)
    last_modified = getattr(result, "last_modified", None)
    return HtmlLinkFetchResult(
        links=list(getattr(result, "links", [])),
        not_modified=bool(getattr(result, "not_modified", False)),
        status_code=int(status_code) if status_code is not None else None,
        etag=etag if isinstance(etag, str) else None,
        last_modified=last_modified if isinstance(last_modified, str) else None,
    )


def _html_link_parser_setting(settings: Settings) -> str | None:
    parser = getattr(settings, "html_link_parser", "auto")
    return parser if isinstance(parser, str) else "auto"


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


def _fetch_source_items(
    *,
    config: SourceConfig,
    db_source_id: int,
    fetch_state: dict[str, object | None] | None,
    enable_fetch_state: bool,
    settings: Settings,
    logger: Logger,
    run_id: str,
    full_text_semaphore: BoundedSemaphore | None,
):  # type: ignore[no-untyped-def]  # pylint: disable=too-many-return-statements
    del db_source_id
    fetcher = Fetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        per_source_min_interval_seconds=settings.per_source_min_interval_seconds,
        http_max_connections=getattr(settings, "fetch_http_max_connections", 20),
        http_max_keepalive_connections=getattr(
            settings, "fetch_http_max_keepalive_connections", 10
        ),
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
        if (
            enable_fetch_state
            and bool(getattr(settings, "fetch_conditional_rss_enabled", True))
            and fetch_state is not None
        ):
            etag = fetch_state.get("etag")
            last_modified = fetch_state.get("last_modified")
            if_none_match = etag if isinstance(etag, str) else None
            if_modified_since = last_modified if isinstance(last_modified, str) else None
        use_explicit_metadata_fetch = (
            enable_fetch_state
            and bool(getattr(settings, "fetch_conditional_rss_enabled", True))
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
    html_two_stage_supported = (
        config.type == "html"
        and all(
            hasattr(settings, attr)
            for attr in ("html_known_streak_stop", "html_max_links_per_source")
        )
    )
    html_conditional_enabled = bool(
        getattr(settings, "fetch_conditional_html_list_enabled", False)
    )
    if config.type == "html" and html_two_stage_supported and (
        fetch_html_links is not _DEFAULT_FETCH_HTML_LINKS
        or fetch_html_article is not _DEFAULT_FETCH_HTML_ARTICLE
    ):
        if_none_match = None
        if_modified_since = None
        if enable_fetch_state and html_conditional_enabled and fetch_state is not None:
            etag = fetch_state.get("etag")
            last_modified = fetch_state.get("last_modified")
            if_none_match = etag if isinstance(etag, str) else None
            if_modified_since = last_modified if isinstance(last_modified, str) else None
        if enable_fetch_state and html_conditional_enabled:
            html_result = fetch_html_links_with_metadata(
                config,
                settings.request_timeout_seconds,
                fetcher=fetcher,
                link_parser=_html_link_parser_setting(settings),
                if_none_match=if_none_match,
                if_modified_since=if_modified_since,
            )
            return _coerce_html_link_fetch_result(html_result)
        return HtmlLinkFetchResult(
            fetch_html_links(
                config,
                settings.request_timeout_seconds,
                fetcher=fetcher,
                link_parser=_html_link_parser_setting(settings),
            )
        )
    if config.type == "html" and fetch_html is not _DEFAULT_FETCH_HTML:
        return fetch_html(
            config,
            settings.request_timeout_seconds,
            fetcher=fetcher,
        )
    if html_two_stage_supported:
        if_none_match = None
        if_modified_since = None
        if enable_fetch_state and html_conditional_enabled and fetch_state is not None:
            etag = fetch_state.get("etag")
            last_modified = fetch_state.get("last_modified")
            if_none_match = etag if isinstance(etag, str) else None
            if_modified_since = last_modified if isinstance(last_modified, str) else None
        if enable_fetch_state and html_conditional_enabled:
            html_result = fetch_html_links_with_metadata(
                config,
                settings.request_timeout_seconds,
                fetcher=fetcher,
                link_parser=_html_link_parser_setting(settings),
                if_none_match=if_none_match,
                if_modified_since=if_modified_since,
            )
            return _coerce_html_link_fetch_result(html_result)
        return HtmlLinkFetchResult(
            fetch_html_links(
                config,
                settings.request_timeout_seconds,
                fetcher=fetcher,
                link_parser=_html_link_parser_setting(settings),
            )
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


def _profiled_source_groups(
    enabled_sources: list[tuple[int, SourceConfig, int, dict[str, object | None] | None, bool]],
    settings: Settings,
) -> list[list[tuple[int, SourceConfig, int, dict[str, object | None] | None, bool]]]:
    profile = str(getattr(settings, "fetch_execution_profile", "balanced") or "balanced")
    if profile not in {"balanced", "rss_fast", "html_heavy"}:
        profile = "balanced"
    if profile == "balanced":
        return [enabled_sources]

    rss_sources = [entry for entry in enabled_sources if entry[1].type == "rss"]
    html_sources = [entry for entry in enabled_sources if entry[1].type == "html"]
    groups = [rss_sources, html_sources] if profile == "rss_fast" else [html_sources, rss_sources]
    return [group for group in groups if group]


def _source_group_max_workers(
    group: list[tuple[int, SourceConfig, int, dict[str, object | None] | None, bool]],
    settings: Settings,
) -> int:
    base_limit = int(settings.concurrency_limit)
    max_workers = int(max(1, min(base_limit, len(group))))
    if not group:
        return max_workers
    source_type = group[0][1].type
    if any(entry[1].type != source_type for entry in group):
        return max_workers
    if source_type == "rss":
        type_limit = getattr(settings, "fetch_rss_concurrency_limit", None)
    elif source_type == "html":
        type_limit = getattr(settings, "fetch_html_concurrency_limit", None)
    else:
        type_limit = None
    if isinstance(type_limit, int) and type_limit > 0:
        max_workers = int(min(max_workers, type_limit))
    return int(max_workers)


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

    for group in _profiled_source_groups(enabled_sources, settings):
        max_workers = _source_group_max_workers(group, settings)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures: dict[Future, tuple[int, SourceConfig, int]] = {
                pool.submit(
                    _fetch_source_items,
                    config=config,
                    db_source_id=db_source_id,
                    fetch_state=fetch_state,
                    enable_fetch_state=enable_fetch_state,
                    settings=settings,
                    logger=logger,
                    run_id=run_id,
                    full_text_semaphore=full_text_semaphore,
                ): (idx, config, db_source_id)
                for idx, config, db_source_id, fetch_state, enable_fetch_state in group
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


def _upsert_article_rows(
    *,
    article_repo: ArticleRepo,
    rows: list[dict[str, object]],
    prefer_batch: bool,
) -> tuple[int, int]:
    if not rows:
        return 0, 0

    batch_upsert = getattr(article_repo, "upsert_articles_batch", None)
    if prefer_batch and callable(batch_upsert):
        batch_result = batch_upsert(rows)
        return int(batch_result[0]), int(batch_result[1])

    new_count = 0
    duplicate_count = 0
    for row in rows:
        _, is_new = article_repo.insert_article(**row)
        if is_new:
            new_count += 1
        else:
            duplicate_count += 1
    return new_count, duplicate_count


def _weekly_report_date_to_publish(today: date) -> date | None:
    if today.weekday() != 0:
        return None
    return today - timedelta(days=1)


def _publish_weekly_analytics_if_due(
    *,
    session: object,
    logger: Logger,
    run_id: str,
    settings: Settings | None = None,
) -> None:
    report_date = _weekly_report_date_to_publish(datetime.now(UTC).date())
    if report_date is None:
        return

    try:
        if settings is not None and settings.weekly_v2_enabled:
            WeeklyStore(cast(Any, session)).enqueue(report_date, settings)
        else:
            WeeklyAnalyticsRepo(cast(Any, session)).save_weekly_report(report_date=report_date)
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.error(
            "weekly_analytics_publish_failed",
            {
                "run_id": run_id,
                "report_date": report_date.isoformat(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        return

    logger.info(
        "weekly_analytics_published",
        {
            "run_id": run_id,
            "report_date": report_date.isoformat(),
        },
    )

# pylint: disable=too-many-branches,too-many-statements
def _process_html_links_two_stage(
    *,
    links: list[str],
    config: SourceConfig,
    db_source_id: int,
    article_repo: ArticleRepo,
    settings: Settings,
    relevance_scorer: JevRelevanceScorer | None = None,
    quality_flags: list[str] | None = None,
) -> tuple[int, int, int, int, bool]:
    new_count = 0
    duplicate_count = 0
    skipped_known_items = 0
    early_stop_hit = False
    fetched_articles = 0
    html_known_streak = 0
    html_known_streak_stop = int(getattr(settings, "html_known_streak_stop", 0) or 0)
    html_max_links_per_source = getattr(settings, "html_max_links_per_source", None)
    batch_mode = bool(getattr(settings, "article_batch_upsert_enabled", False))
    exists_by_canonical_hash = getattr(article_repo, "exists_by_canonical_hash", None)
    exists_by_canonical_hash_fn = (
        exists_by_canonical_hash if callable(exists_by_canonical_hash) else None
    )
    existing_canonical_hashes = getattr(article_repo, "existing_canonical_hashes", None)
    existing_canonical_hashes_fn = (
        existing_canonical_hashes if callable(existing_canonical_hashes) else None
    )
    links = [link for link in links if url_exclusion_reason(str(link)) is None]
    capped_links = links
    if isinstance(html_max_links_per_source, int) and html_max_links_per_source >= 0:
        capped_links = links[:html_max_links_per_source]
        if len(capped_links) < len(links) and quality_flags is not None:
            quality_flags.append("truncated")
    canonical_by_link: list[tuple[str, str, str]] = [
        (
            str(link),
            canonicalize_url(str(link)),
            canonical_url_hash(str(link)),
        )
        for link in capped_links
    ]
    known_hashes: set[str] = set()
    if existing_canonical_hashes_fn is not None:
        known_hashes = existing_canonical_hashes_fn([h for _, _, h in canonical_by_link])
    queued_rows: list[dict[str, object]] = []
    fetcher = Fetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        per_source_min_interval_seconds=settings.per_source_min_interval_seconds,
        http_max_connections=getattr(settings, "fetch_http_max_connections", 20),
        http_max_keepalive_connections=getattr(
            settings, "fetch_http_max_keepalive_connections", 10
        ),
    )

    try:
        for link, canonical, canonical_hash in canonical_by_link:
            is_known = False
            if existing_canonical_hashes_fn is not None:
                is_known = canonical_hash in known_hashes
            elif exists_by_canonical_hash_fn is not None:
                is_known = exists_by_canonical_hash_fn(canonical_hash)
            if is_known:
                duplicate_count += 1
                skipped_known_items += 1
                html_known_streak += 1
                if 0 < html_known_streak_stop <= html_known_streak:
                    early_stop_hit = True
                    break
                continue

            html_known_streak = 0
            try:
                item = fetch_html_article(
                    source=config,
                    url=str(link),
                    timeout_seconds=settings.request_timeout_seconds,
                    fetcher=fetcher,
                )
            except Exception:
                if quality_flags is not None:
                    quality_flags.append("article_failure")
                continue
            if item is None:
                if quality_flags is not None:
                    quality_flags.append("parser_failure")
                continue
            reason = _item_exclusion_reason(item)
            if reason:
                log_exclusion(str(item.url), reason)
                continue
            fetched_articles += 1
            _record_weekly_observation(article_repo, db_source_id, item)
            if (item.published_at is None and item.publication_evidence_at is None
                    and quality_flags is not None):
                quality_flags.append("unknown_publication_date")

            assessment = relevance_scorer.classify(item) if relevance_scorer is not None else None
            relevance = assessment.relevance_score if assessment is not None else None
            if relevance is None:
                relevance = ai_relevance_score(item)
            freshness = freshness_score(item.published_at)
            rank = rank_score(
                relevance=relevance,
                freshness=freshness,
                source_weight=config.source_weight,
            )
            row: dict[str, object] = {
                "source_id": db_source_id,
                "title": item.title,
                "url": str(item.url),
                "url_canonical": canonical,
                "url_canonical_hash": canonical_hash,
                "published_at": item.published_at or datetime.now(UTC),
                "summary": item.summary,
                "content": item.content,
                "ai_relevance_score": relevance,
                "freshness_score": freshness,
                "rank_score": rank,
            }
            if assessment is not None and assessment.category is not None:
                row["category"] = assessment.category
                row["category_confidence"] = assessment.category_confidence
            if batch_mode:
                queued_rows.append(row)
            else:
                _, is_new = article_repo.insert_article(**row)
                if is_new:
                    new_count += 1
                else:
                    duplicate_count += 1
            if existing_canonical_hashes_fn is not None or batch_mode:
                known_hashes.add(canonical_hash)
        if batch_mode:
            batch_new, batch_duplicates = _upsert_article_rows(
                article_repo=article_repo,
                rows=queued_rows,
                prefer_batch=True,
            )
            new_count += batch_new
            duplicate_count += batch_duplicates
    finally:
        fetcher.close()
    return fetched_articles, new_count, duplicate_count, skipped_known_items, early_stop_hit


def _persist_fetch_state_if_present(
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
    ) or bool(getattr(result, "not_modified", False))
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


def _record_weekly_observation(article_repo: ArticleRepo, source_id: int, item: Any) -> None:
    session = getattr(article_repo, "session", None)
    if isinstance(session, Session):
        record_observation(session, source_id, item)


def _item_exclusion_reason(item: Any) -> str | None:
    if getattr(item, "page_eligibility_checked", False):
        reason = url_exclusion_reason(str(item.url))
    else:
        reason = text_exclusion_reason(
            str(item.url), item.title, item.content or item.summary or "")
    return cast(str | None, reason)


def _process_fetched_source_items(
    *,
    items: list,
    config: SourceConfig,
    db_source_id: int,
    article_repo: ArticleRepo,
    settings: Settings,
    relevance_scorer: JevRelevanceScorer | None = None,
) -> tuple[int, int, int, bool]:
    new_count = 0
    duplicate_count = 0
    skipped_known_items = 0
    early_stop_hit = False
    rss_known_streak = 0
    rss_known_streak_stop = int(getattr(settings, "rss_known_streak_stop", 0) or 0)
    batch_mode = bool(getattr(settings, "article_batch_upsert_enabled", False))
    exists_by_canonical_hash = getattr(article_repo, "exists_by_canonical_hash", None)
    exists_by_canonical_hash_fn = (
        exists_by_canonical_hash if callable(exists_by_canonical_hash) else None
    )
    use_rss_early_stop = (
        config.type == "rss"
        and rss_known_streak_stop > 0
        and exists_by_canonical_hash_fn is not None
    )
    queued_rows_by_hash: dict[str, dict[str, object]] = {}
    accepted_items = []
    for item in items:
        reason = _item_exclusion_reason(item)
        if reason:
            log_exclusion(str(item.url), reason)
        else:
            accepted_items.append(item)
    items = accepted_items

    # The RSS feed has already been parsed in full. Preserve observations even
    # when legacy ingestion later stops at a streak of known URLs.
    for item in items:
        _record_weekly_observation(article_repo, db_source_id, item)

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

        assessment = relevance_scorer.classify(item) if relevance_scorer is not None else None
        relevance = assessment.relevance_score if assessment is not None else None
        if relevance is None:
            relevance = ai_relevance_score(item)
        freshness = freshness_score(item.published_at)
        rank = rank_score(
            relevance=relevance,
            freshness=freshness,
            source_weight=config.source_weight,
        )
        row: dict[str, object] = {
            "source_id": db_source_id,
            "title": item.title,
            "url": str(item.url),
            "url_canonical": canonical,
            "url_canonical_hash": canonical_hash,
            "published_at": item.published_at or datetime.now(UTC),
            "summary": item.summary,
            "content": item.content,
            "ai_relevance_score": relevance,
            "freshness_score": freshness,
            "rank_score": rank,
        }
        if assessment is not None and assessment.category is not None:
            row["category"] = assessment.category
            row["category_confidence"] = assessment.category_confidence
        if batch_mode:
            existing_row = queued_rows_by_hash.get(canonical_hash)
            if existing_row is not None:
                existing_row["ai_relevance_score"] = row["ai_relevance_score"]
                existing_row["freshness_score"] = row["freshness_score"]
                existing_row["rank_score"] = row["rank_score"]
                if row.get("category") is not None:
                    existing_row["category"] = row["category"]
                    existing_row["category_confidence"] = row["category_confidence"]
                duplicate_count += 1
                continue
            queued_rows_by_hash[canonical_hash] = row
        else:
            _, is_new = article_repo.insert_article(**row)
            if is_new:
                new_count += 1
            else:
                duplicate_count += 1

    if batch_mode:
        batch_new, batch_duplicates = _upsert_article_rows(
            article_repo=article_repo,
            rows=list(queued_rows_by_hash.values()),
            prefer_batch=True,
        )
        new_count += batch_new
        duplicate_count += batch_duplicates

    return new_count, duplicate_count, skipped_known_items, early_stop_hit


def _process_source_result(
    *,
    fetch_result: object,
    config: SourceConfig,
    db_source_id: int,
    source_repo: SourceRepo,
    article_repo: ArticleRepo,
    settings: Settings,
    metrics: SourceMetrics,
    relevance_scorer: JevRelevanceScorer | None = None,
) -> None:
    metrics.coverage_complete = bool(getattr(fetch_result, "coverage_complete", True))
    if config.type in {"rss", "html"}:
        _persist_fetch_state_if_present(
            source_repo=source_repo,
            db_source_id=db_source_id,
            result=fetch_result,
        )
        if bool(getattr(fetch_result, "not_modified", False)):
            metrics.not_modified = True
            return

    if config.type == "html" and isinstance(fetch_result, HtmlLinkFetchResult):
        quality_flags: list[str] = []
        (
            metrics.fetched_items,
            metrics.new_items,
            metrics.duplicate_items,
            metrics.skipped_known_items,
            metrics.early_stop_hit,
        ) = _process_html_links_two_stage(
            links=fetch_result.links,
            config=config,
            db_source_id=db_source_id,
            article_repo=article_repo,
            settings=settings,
            relevance_scorer=relevance_scorer,
            quality_flags=quality_flags,
        )
        metrics.coverage_complete = metrics.coverage_complete and not quality_flags
        return

    items = _fetch_result_items(fetch_result)
    if any(item.published_at is None or getattr(item, "publication_date_kind", "published")
           != "published" for item in items):
        metrics.coverage_complete = False
    metrics.fetched_items = len(items)
    (
        metrics.new_items,
        metrics.duplicate_items,
        metrics.skipped_known_items,
        metrics.early_stop_hit,
    ) = _process_fetched_source_items(
        items=items,
        config=config,
        db_source_id=db_source_id,
        article_repo=article_repo,
        settings=settings,
        relevance_scorer=relevance_scorer,
    )


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
    with SessionLocal() as session, jev_relevance_scorer(settings, logger) as relevance_scorer:
        source_repo = SourceRepo(session)
        article_repo = ArticleRepo(session)
        enabled_sources: list[
            tuple[int, SourceConfig, int, dict[str, object | None] | None, bool]
        ] = []
        configured_source_keys: set[str] = set()
        weekly_versions: dict[int, str] = {}

        for idx, config in enumerate(configs):
            configured_source_keys.add(config.id)
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
                    bool(supports_fetch_state),
                )
            )

        list_enabled_sources = getattr(source_repo, "list_enabled_sources", None)
        if callable(list_enabled_sources):
            next_index = len(configs)
            for source in list_enabled_sources():
                source_model = cast(Any, source)
                source_key = str(source_model.source_key)
                if source_key in configured_source_keys:
                    continue
                config = _managed_source_to_config(source_model)
                source_id = int(source_model.id)
                fetch_state, supports_fetch_state = _source_repo_get_fetch_state(
                    source_repo,
                    source_id=source_id,
                )
                enabled_sources.append(
                    (
                        next_index,
                        config,
                        source_id,
                        fetch_state,
                        bool(supports_fetch_state),
                    )
                )
                next_index += 1

        if isinstance(session, Session):
            for _, config, source_id, _, _ in enabled_sources:
                weekly_versions[source_id] = register_source(
                    session, source_id, config, settings, datetime.now(UTC))

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
                if isinstance(session, Session):
                    record_attempt(session, run_id=run_id, source_id=db_source_id,
                                   version_id=weekly_versions[db_source_id],
                                   interval=config.fetch_interval_minutes, outcome="fetch_failure",
                                   complete=True, now=datetime.now(UTC))
                continue

            source_metrics = SourceMetrics(source_id=config.id, source_type=config.type)
            try:
                # Keep articles and cache validators atomic so failed sources can be retried.
                with session.begin_nested():
                    _process_source_result(
                        fetch_result=fetch_result,
                        config=config,
                        db_source_id=db_source_id,
                        source_repo=source_repo,
                        article_repo=article_repo,
                        settings=settings,
                        metrics=source_metrics,
                        relevance_scorer=relevance_scorer,
                    )
            except Exception as exc:
                source_metrics.new_items = 0
                source_metrics.duplicate_items = 0
                source_metrics.skipped_known_items = 0
                source_metrics.early_stop_hit = False
                source_metrics.not_modified = False
                source_metrics.errors = 1
                source_metrics.coverage_complete = False
                error_count += 1
                logger.error(
                    "source_persist_failed",
                    {
                        "run_id": run_id,
                        "source_id": config.id,
                        "stage": "persist",
                        "url": str(config.url),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )

            fetched_count += source_metrics.fetched_items
            if isinstance(session, Session):
                outcome = ("persist_failure" if source_metrics.errors else (
                    "parser_failure" if not source_metrics.coverage_complete else (
                    "not_modified" if source_metrics.not_modified else (
                        "success" if source_metrics.fetched_items else "empty"))))
                record_attempt(session, run_id=run_id, source_id=db_source_id,
                               version_id=weekly_versions[db_source_id],
                               interval=config.fetch_interval_minutes, outcome=outcome,
                               complete=(source_metrics.coverage_complete and not (
                                   config.type == "html" and source_metrics.early_stop_hit)),
                               now=datetime.now(UTC))
            new_count += source_metrics.new_items
            duplicate_count += source_metrics.duplicate_items
            optimization_not_modified_sources += int(source_metrics.not_modified)
            optimization_early_stop_hits += int(source_metrics.early_stop_hit)
            if config.type == "html":
                optimization_skipped_known_html_links += source_metrics.skipped_known_items
            _log_source_metrics(
                logger=logger,
                run_id=run_id,
                metrics=source_metrics,
                enabled=bool(getattr(settings, "fetch_emit_source_metrics", True)),
            )

        _publish_weekly_analytics_if_due(session=session, logger=logger, run_id=run_id,
                                       settings=settings)
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
        source_count=len(enabled_sources),
        fetched=fetched_count,
        new=new_count,
        duplicates=duplicate_count,
        errors=error_count,
        not_modified_sources=optimization_not_modified_sources,
        skipped_known_html_links=optimization_skipped_known_html_links,
        early_stop_hits=optimization_early_stop_hits,
    )
