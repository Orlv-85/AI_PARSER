"""Fetch cycle: sources, conditional fetch, page filter, semantic admission, scoring, articles.

Behavior, decisions, invariants and code map: pipeline.md in the parent directory.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from logging import Logger
from threading import BoundedSemaphore
from typing import Any, cast

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.config.sources import SourceConfig, load_sources
from app.core.ingestion.pipeline.fetch import _collect_fetched_items
from app.core.ingestion.pipeline.models import (
    AdmissionState,
    EnabledSource,
    FetchResult,
    FetchSummary,
    SourceMetrics,
)
from app.core.ingestion.pipeline.replay import _replay_pending_for_source
from app.core.ingestion.pipeline.screening import _admission_snapshot, _restore_admission
from app.core.ingestion.pipeline.source_result import _log_source_metrics, _process_source_result
from app.core.ingestion.pipeline.sources import _clear_source_validators, _managed_source_to_config
from app.core.jev import JevRelevanceScorer, jev_relevance_scorer
from app.storage import SessionLocal, create_all
from app.storage.admission import (
    clear_collection_paused,
    set_collection_paused,
)
from app.storage.article_repo import ArticleRepo
from app.storage.source_repo import SourceRepo

_Snapshot = tuple[int, int, int, int, bool]


@dataclass
class _RunTotals:  # pylint: disable=too-many-instance-attributes
    fetched: int = 0
    examined: int = 0
    new: int = 0
    duplicates: int = 0
    errors: int = 0
    not_modified_sources: int = 0
    skipped_known_html_links: int = 0
    early_stop_hits: int = 0
    sources_fetched: int = 0
    semantic_rejected: int = 0
    semantic_unresolved: int = 0
    semantic_cache_hits: int = 0


@dataclass
class _CycleContext:  # pylint: disable=too-many-instance-attributes
    settings: Settings
    logger: Logger
    run_id: str
    session: Session
    source_repo: SourceRepo
    article_repo: ArticleRepo
    relevance_scorer: JevRelevanceScorer | None
    admission_state: AdmissionState
    full_text_semaphore: BoundedSemaphore | None


def _collect_enabled_sources(
    configs: list[SourceConfig], source_repo: SourceRepo,
) -> list[EnabledSource]:
    enabled_sources: list[EnabledSource] = []
    configured_source_keys: set[str] = set()
    for idx, config in enumerate(configs):
        configured_source_keys.add(config.id)
        db_source = source_repo.upsert_source(config)
        if not config.enabled:
            continue
        enabled_sources.append((
            idx, config, db_source.id, source_repo.get_fetch_state(source_id=db_source.id),
        ))

    next_index = len(configs)
    for source in source_repo.list_enabled_sources():
        source_model = cast(Any, source)
        source_key = str(source_model.source_key)
        if source_key in configured_source_keys:
            continue
        config = _managed_source_to_config(source_model)
        source_id = int(source_model.id)
        enabled_sources.append((
            next_index, config, source_id, source_repo.get_fetch_state(source_id=source_id),
        ))
        next_index += 1
    return enabled_sources


def _merge_fresh_metrics(source_metrics: SourceMetrics, fresh_metrics: SourceMetrics) -> None:
    source_metrics.fetched_items += fresh_metrics.fetched_items
    source_metrics.examined_items += fresh_metrics.examined_items
    source_metrics.new_items += fresh_metrics.new_items
    source_metrics.duplicate_items += fresh_metrics.duplicate_items
    source_metrics.skipped_known_items += fresh_metrics.skipped_known_items
    source_metrics.early_stop_hit = fresh_metrics.early_stop_hit
    source_metrics.not_modified = fresh_metrics.not_modified
    source_metrics.acquisition_stopped = (
        source_metrics.acquisition_stopped or fresh_metrics.acquisition_stopped
    )
    source_metrics.coverage_complete = (
        source_metrics.coverage_complete and fresh_metrics.coverage_complete
    )


def _process_source_with_admission(
    ctx: _CycleContext,
    totals: _RunTotals,
    *,
    source: EnabledSource,
    source_metrics: SourceMetrics,
) -> None:
    """Replay pending candidates, then fetch and process the source in one savepoint."""
    idx, config, db_source_id, _fetch_state = source
    state = ctx.admission_state
    with ctx.session.begin_nested():
        replay_count = _replay_pending_for_source(
            session=ctx.session,
            config=config,
            db_source_id=db_source_id,
            article_repo=ctx.article_repo,
            settings=ctx.settings,
            relevance_scorer=ctx.relevance_scorer,
            admission_state=state,
            metrics=source_metrics,
        )
        source_metrics.replay_items += replay_count
        if not state.paused:
            fetched, errors = _collect_fetched_items(
                enabled_sources=[source],
                settings=ctx.settings,
                logger=ctx.logger,
                run_id=ctx.run_id,
                full_text_semaphore=ctx.full_text_semaphore,
            )
            totals.errors += errors
            fetch_result = fetched.get(idx)
            source_metrics.errors += int(fetch_result is None)
            if fetch_result is not None:
                fresh_metrics = SourceMetrics(source_id=config.id, source_type=config.type)
                _process_source_result(
                    fetch_result=fetch_result,
                    config=config,
                    db_source_id=db_source_id,
                    source_repo=ctx.source_repo,
                    article_repo=ctx.article_repo,
                    settings=ctx.settings,
                    metrics=fresh_metrics,
                    relevance_scorer=ctx.relevance_scorer,
                    admission_state=state,
                )
                _merge_fresh_metrics(source_metrics, fresh_metrics)
        if state.paused:
            _clear_source_validators(ctx.source_repo, db_source_id)


def _process_prefetched_source(
    ctx: _CycleContext,
    *,
    source: EnabledSource,
    fetched_by_index: dict[int, FetchResult],
    source_metrics: SourceMetrics,
) -> bool:
    """Process a prefetched source; False when its fetch failed and the source is skipped."""
    idx, config, db_source_id, _fetch_state = source
    fetch_result = fetched_by_index.get(idx)
    if fetch_result is None:
        source_metrics.errors = 1
        _log_source_metrics(
            logger=ctx.logger,
            run_id=ctx.run_id,
            metrics=source_metrics,
            enabled=ctx.settings.fetch_emit_source_metrics,
        )
        return False
    with ctx.session.begin_nested():
        _process_source_result(
            fetch_result=fetch_result,
            config=config,
            db_source_id=db_source_id,
            source_repo=ctx.source_repo,
            article_repo=ctx.article_repo,
            settings=ctx.settings,
            metrics=source_metrics,
            relevance_scorer=ctx.relevance_scorer,
            admission_state=ctx.admission_state,
        )
    return True


def _record_persist_failure(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    ctx: _CycleContext,
    totals: _RunTotals,
    config: SourceConfig,
    source_metrics: SourceMetrics,
    snapshot: _Snapshot,
    exc: Exception,
) -> None:
    _restore_admission(ctx.admission_state, snapshot)
    source_metrics.new_items = 0
    source_metrics.duplicate_items = 0
    source_metrics.skipped_known_items = 0
    source_metrics.early_stop_hit = False
    source_metrics.not_modified = False
    source_metrics.errors = 1
    source_metrics.coverage_complete = False
    totals.errors += 1
    ctx.logger.error(
        "source_persist_failed",
        {
            "run_id": ctx.run_id,
            "source_id": config.id,
            "stage": "persist",
            "url": str(config.url),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        },
    )


def _finish_source(
    ctx: _CycleContext,
    totals: _RunTotals,
    config: SourceConfig,
    source_metrics: SourceMetrics,
    snapshot: _Snapshot,
) -> None:
    state = ctx.admission_state
    if state.paused:
        set_collection_paused(ctx.session)
    source_metrics.semantic_rejected = state.rejected - snapshot[1]
    source_metrics.semantic_unresolved = state.unresolved - snapshot[2]
    source_metrics.semantic_cache_hits = state.cache_hits - snapshot[0]
    source_metrics.screening_paused = state.paused
    totals.semantic_rejected += source_metrics.semantic_rejected
    totals.semantic_unresolved += source_metrics.semantic_unresolved
    totals.semantic_cache_hits += source_metrics.semantic_cache_hits
    totals.fetched += source_metrics.fetched_items
    totals.examined += source_metrics.examined_items
    totals.new += source_metrics.new_items
    totals.duplicates += source_metrics.duplicate_items
    totals.not_modified_sources += int(source_metrics.not_modified)
    totals.early_stop_hits += int(source_metrics.early_stop_hit)
    if config.type == "html":
        totals.skipped_known_html_links += source_metrics.skipped_known_items
    _log_source_metrics(
        logger=ctx.logger,
        run_id=ctx.run_id,
        metrics=source_metrics,
        enabled=ctx.settings.fetch_emit_source_metrics,
    )


def _run_sources(
    ctx: _CycleContext,
    totals: _RunTotals,
    enabled_sources: list[EnabledSource],
    fetched_by_index: dict[int, FetchResult],
) -> None:
    for source in enabled_sources:
        config = source[1]
        if ctx.admission_state.paused:
            break
        source_metrics = SourceMetrics(source_id=config.id, source_type=config.type)
        totals.sources_fetched += 1
        snapshot = _admission_snapshot(ctx.admission_state)
        try:
            if ctx.admission_state.enabled:
                _process_source_with_admission(
                    ctx, totals, source=source, source_metrics=source_metrics,
                )
            elif not _process_prefetched_source(
                ctx, source=source, fetched_by_index=fetched_by_index,
                source_metrics=source_metrics,
            ):
                continue
        except Exception as exc:
            _record_persist_failure(ctx, totals, config, source_metrics, snapshot, exc)

        _finish_source(ctx, totals, config, source_metrics, snapshot)
        if ctx.admission_state.paused:
            break


def run_fetch_cycle(*, settings: Settings, logger: Logger) -> FetchSummary:
    configs = load_sources(settings.sources_path)
    create_all()

    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    totals = _RunTotals()
    full_text_semaphore = (
        BoundedSemaphore(settings.rss_full_text_concurrency_limit)
        if settings.rss_full_text_concurrency_limit
        and settings.rss_full_text_concurrency_limit > 0
        else None
    )
    admission_state = AdmissionState(enabled=settings.semantic_admission_enabled)
    with SessionLocal() as session, jev_relevance_scorer(settings, logger) as relevance_scorer:
        ctx = _CycleContext(
            settings=settings,
            logger=logger,
            run_id=run_id,
            session=session,
            source_repo=SourceRepo(session),
            article_repo=ArticleRepo(session),
            relevance_scorer=relevance_scorer,
            admission_state=admission_state,
            full_text_semaphore=full_text_semaphore,
        )
        enabled_sources = _collect_enabled_sources(configs, ctx.source_repo)

        if admission_state.enabled and relevance_scorer is None:
            set_collection_paused(session)
            session.commit()
            logger.error(
                "screening_unavailable",
                {"run_id": run_id, "reason": "provider_missing_or_disabled"},
            )
            return FetchSummary(
                run_id=run_id,
                source_count=len(enabled_sources),
                fetched=0,
                new=0,
                duplicates=0,
                errors=0,
                screening_paused=1,
            )

        fetched_by_index: dict[int, FetchResult] = {}
        if not admission_state.enabled:
            fetched_by_index, fetch_errors = _collect_fetched_items(
                enabled_sources=enabled_sources,
                settings=settings,
                logger=logger,
                run_id=run_id,
                full_text_semaphore=full_text_semaphore,
            )
            totals.errors += fetch_errors

        _run_sources(ctx, totals, enabled_sources, fetched_by_index)

        if not admission_state.paused and admission_state.fresh_success:
            clear_collection_paused(session)
        session.commit()

    logger.info(
        "fetch_run_finished",
        {
            "run_id": run_id,
            "fetched": totals.fetched,
            "examined": totals.examined,
            "sources_fetched": totals.sources_fetched,
            "new": totals.new,
            "duplicates": totals.duplicates,
            "errors": totals.errors,
            "not_modified_sources": totals.not_modified_sources,
            "skipped_known_html_links": totals.skipped_known_html_links,
            "early_stop_hits": totals.early_stop_hits,
        },
    )
    return FetchSummary(
        run_id=run_id,
        source_count=len(enabled_sources),
        fetched=totals.fetched,
        new=totals.new,
        duplicates=totals.duplicates,
        errors=totals.errors,
        not_modified_sources=totals.not_modified_sources,
        skipped_known_html_links=totals.skipped_known_html_links,
        early_stop_hits=totals.early_stop_hits,
        semantic_rejected=totals.semantic_rejected,
        semantic_unresolved=totals.semantic_unresolved,
        semantic_cache_hits=totals.semantic_cache_hits,
        screening_paused=int(admission_state.paused),
        examined=totals.examined,
        sources_fetched=totals.sources_fetched,
    )
