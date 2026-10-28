"""Fetch cycle: sources, conditional fetch, page filter, semantic admission, scoring, articles.

Behavior, decisions, invariants and code map: pipeline.md in the parent directory.
"""
from datetime import UTC, datetime
from logging import Logger
from threading import BoundedSemaphore
from typing import Any, cast

from app.config.settings import Settings
from app.config.sources import load_sources
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
from app.core.jev import jev_relevance_scorer
from app.storage import SessionLocal, create_all
from app.storage.admission import (
    clear_collection_paused,
    set_collection_paused,
)
from app.storage.article_repo import ArticleRepo
from app.storage.source_repo import SourceRepo


# pylint: disable=too-many-branches,too-many-statements
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
    examined_count = 0
    sources_fetched = 0
    full_text_semaphore = (
        BoundedSemaphore(settings.rss_full_text_concurrency_limit)
        if settings.rss_full_text_concurrency_limit
        and settings.rss_full_text_concurrency_limit > 0
        else None
    )
    admission_state = AdmissionState(enabled=settings.semantic_admission_enabled)
    with SessionLocal() as session, jev_relevance_scorer(settings, logger) as relevance_scorer:
        source_repo = SourceRepo(session)
        article_repo = ArticleRepo(session)
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
            error_count += fetch_errors

        run_semantic_rejected = 0
        run_semantic_unresolved = 0
        run_semantic_cache_hits = 0
        for idx, config, db_source_id, fetch_state in enabled_sources:
            if admission_state.paused:
                break
            source_metrics = SourceMetrics(source_id=config.id, source_type=config.type)
            sources_fetched += 1
            snapshot = _admission_snapshot(admission_state)
            fetch_result: FetchResult | None = None
            fetch_failed = False
            try:
                if admission_state.enabled:
                    with session.begin_nested():
                        replay_count = _replay_pending_for_source(
                            session=session,
                            config=config,
                            db_source_id=db_source_id,
                            article_repo=article_repo,
                            settings=settings,
                            relevance_scorer=relevance_scorer,
                            admission_state=admission_state,
                            metrics=source_metrics,
                        )
                        source_metrics.replay_items += replay_count
                        if not admission_state.paused:
                            one_source = [(idx, config, db_source_id, fetch_state)]
                            fetched, errors = _collect_fetched_items(
                                enabled_sources=one_source,
                                settings=settings,
                                logger=logger,
                                run_id=run_id,
                                full_text_semaphore=full_text_semaphore,
                            )
                            error_count += errors
                            fetch_result = fetched.get(idx)
                            fetch_failed = fetch_result is None
                            source_metrics.errors += int(fetch_failed)
                            if fetch_result is not None:
                                fresh_metrics = SourceMetrics(
                                    source_id=config.id, source_type=config.type,
                                )
                                _process_source_result(
                                    fetch_result=fetch_result,
                                    config=config,
                                    db_source_id=db_source_id,
                                    source_repo=source_repo,
                                    article_repo=article_repo,
                                    settings=settings,
                                    metrics=fresh_metrics,
                                    relevance_scorer=relevance_scorer,
                                    admission_state=admission_state,
                                )
                                source_metrics.fetched_items += fresh_metrics.fetched_items
                                source_metrics.examined_items += fresh_metrics.examined_items
                                source_metrics.new_items += fresh_metrics.new_items
                                source_metrics.duplicate_items += fresh_metrics.duplicate_items
                                source_metrics.skipped_known_items += (
                                    fresh_metrics.skipped_known_items
                                )
                                source_metrics.early_stop_hit = fresh_metrics.early_stop_hit
                                source_metrics.not_modified = fresh_metrics.not_modified
                                source_metrics.acquisition_stopped = (
                                    source_metrics.acquisition_stopped
                                    or fresh_metrics.acquisition_stopped
                                )
                                source_metrics.coverage_complete = (
                                    source_metrics.coverage_complete
                                    and fresh_metrics.coverage_complete
                                )
                        if admission_state.paused:
                            _clear_source_validators(source_repo, db_source_id)
                else:
                    fetch_result = fetched_by_index.get(idx)
                    if fetch_result is None:
                        source_metrics.errors = 1
                        _log_source_metrics(
                            logger=logger,
                            run_id=run_id,
                            metrics=source_metrics,
                            enabled=settings.fetch_emit_source_metrics,
                        )
                        continue
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
                            admission_state=admission_state,
                        )
            except Exception as exc:
                _restore_admission(admission_state, snapshot)
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

            if admission_state.paused:
                set_collection_paused(session)
            source_metrics.semantic_rejected = admission_state.rejected - snapshot[1]
            source_metrics.semantic_unresolved = admission_state.unresolved - snapshot[2]
            source_metrics.semantic_cache_hits = admission_state.cache_hits - snapshot[0]
            source_metrics.screening_paused = admission_state.paused
            run_semantic_rejected += source_metrics.semantic_rejected
            run_semantic_unresolved += source_metrics.semantic_unresolved
            run_semantic_cache_hits += source_metrics.semantic_cache_hits
            fetched_count += source_metrics.fetched_items
            examined_count += source_metrics.examined_items
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
                enabled=settings.fetch_emit_source_metrics,
            )
            if admission_state.paused:
                break

        if not admission_state.paused and admission_state.fresh_success:
            clear_collection_paused(session)
        session.commit()

    logger.info(
        "fetch_run_finished",
        {
            "run_id": run_id,
            "fetched": fetched_count,
            "examined": examined_count,
            "sources_fetched": sources_fetched,
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
        semantic_rejected=run_semantic_rejected,
        semantic_unresolved=run_semantic_unresolved,
        semantic_cache_hits=run_semantic_cache_hits,
        screening_paused=int(admission_state.paused),
        examined=examined_count,
        sources_fetched=sources_fetched,
    )
