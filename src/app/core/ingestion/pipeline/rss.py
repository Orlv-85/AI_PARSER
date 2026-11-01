"""RSS path: persist the items of one fetched feed."""


from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.ingestion.admission import (
    admission_cache_key,
    bounded_evidence,
    evidence_hash,
)
from app.core.ingestion.pipeline.models import AdmissionState, SourceMetrics
from app.core.ingestion.pipeline.rows import (
    _build_article_row,
    _candidate_payload,
    _item_exclusion_reason,
    _upsert_article_rows,
)
from app.core.ingestion.pipeline.screening import _screen_candidate
from app.core.jev import JevAssessment, JevRelevanceScorer
from app.ingest.page_filter import (
    log_exclusion,
)
from app.storage.admission import (
    upsert_pending,
)
from app.storage.article_repo import ArticleRepo


def _accepted_items(items: list) -> list:
    accepted_items = []
    for item in items:
        reason = _item_exclusion_reason(item)
        if reason:
            log_exclusion(str(item.url), reason)
        else:
            accepted_items.append(item)
    return accepted_items


def _queue_pending_candidates(
    *,
    items: list,
    config: SourceConfig,
    db_source_id: int,
    article_repo: ArticleRepo,
    settings: Settings,
    use_known_skip: bool,
) -> None:
    for item in items:
        identity_url = getattr(item, "ingestion_canonical_url", None) or str(item.url)
        canonical_hash = canonical_url_hash(identity_url)
        if use_known_skip and article_repo.exists_by_canonical_hash(canonical_hash):
            continue
        evidence = bounded_evidence(item)
        ev_hash = evidence_hash(evidence)
        key = admission_cache_key(
            url_canonical_hash=canonical_hash,
            evidence_hash=ev_hash,
            model=settings.jev_model,
            policy_version=settings.semantic_admission_policy_version,
            prompt_version=settings.semantic_admission_prompt_version,
        )
        upsert_pending(
            article_repo.session,
            key=key,
            url_canonical_hash=canonical_hash,
            source_id=db_source_id,
            payload=_candidate_payload(item, config),
            evidence_hash=ev_hash,
            policy_version=settings.semantic_admission_policy_version,
            model=settings.jev_model,
        )


def _merge_queued_row(existing_row: dict[str, object], row: dict[str, object]) -> None:
    existing_row["ai_relevance_score"] = row["ai_relevance_score"]
    existing_row["freshness_score"] = row["freshness_score"]
    existing_row["rank_score"] = row["rank_score"]
    if row.get("category") is not None:
        existing_row["category"] = row["category"]
        existing_row["category_confidence"] = row["category_confidence"]


def _assess_item(
    *,
    item: object,
    config: SourceConfig,
    db_source_id: int,
    article_repo: ArticleRepo,
    settings: Settings,
    relevance_scorer: JevRelevanceScorer | None,
    admission_state: AdmissionState | None,
    canonical_hash: str,
    canonical: str,
) -> tuple[str, JevAssessment | None]:
    if admission_state is not None and admission_state.enabled:
        screened: tuple[str, JevAssessment | None] = _screen_candidate(
            item=item,
            config=config,
            db_source_id=db_source_id,
            article_repo=article_repo,
            settings=settings,
            relevance_scorer=relevance_scorer,
            admission_state=admission_state,
            canonical_hash=canonical_hash,
            canonical_url=canonical,
        )
        return screened
    return "accept", relevance_scorer.classify(item) if relevance_scorer is not None else None


def _stage_row(
    *,
    row: dict[str, object],
    canonical_hash: str,
    batch_mode: bool,
    queued_rows_by_hash: dict[str, dict[str, object]],
    article_repo: ArticleRepo,
) -> tuple[int, int]:
    """Return (new, duplicate) counts for one row; batch mode only queues it."""
    if batch_mode:
        existing_row = queued_rows_by_hash.get(canonical_hash)
        if existing_row is None:
            queued_rows_by_hash[canonical_hash] = row
            return 0, 0
        _merge_queued_row(existing_row, row)
        return 0, 1
    _, is_new = article_repo.insert_article(**row)
    return (1, 0) if is_new else (0, 1)


def _process_fetched_source_items(
    *,
    items: list,
    config: SourceConfig,
    db_source_id: int,
    article_repo: ArticleRepo,
    settings: Settings,
    relevance_scorer: JevRelevanceScorer | None = None,
    admission_state: AdmissionState | None = None,
    metrics: SourceMetrics | None = None,
) -> tuple[int, int, int, bool]:
    new_count = 0
    duplicate_count = 0
    skipped_known_items = 0
    early_stop_hit = False
    rss_known_streak = 0
    rss_known_streak_stop = settings.rss_known_streak_stop
    batch_mode = settings.article_batch_upsert_enabled
    admission_enabled = admission_state is not None and admission_state.enabled
    use_rss_early_stop = config.type == "rss" and rss_known_streak_stop > 0
    use_known_skip = admission_enabled or use_rss_early_stop
    queued_rows_by_hash: dict[str, dict[str, object]] = {}
    items = _accepted_items(items)

    if admission_enabled:
        _queue_pending_candidates(
            items=items,
            config=config,
            db_source_id=db_source_id,
            article_repo=article_repo,
            settings=settings,
            use_known_skip=use_known_skip,
        )

    for item in items:
        if metrics is not None:
            metrics.examined_items += 1
        identity_url = getattr(item, "ingestion_canonical_url", None) or str(item.url)
        canonical = canonicalize_url(identity_url)
        canonical_hash = canonical_url_hash(identity_url)
        if use_known_skip and article_repo.exists_by_canonical_hash(canonical_hash):
            duplicate_count += 1
            skipped_known_items += 1
            if use_rss_early_stop:
                rss_known_streak += 1
                if rss_known_streak >= rss_known_streak_stop:
                    early_stop_hit = True
                    break
            continue
        if use_rss_early_stop:
            rss_known_streak = 0

        action, assessment = _assess_item(
            item=item,
            config=config,
            db_source_id=db_source_id,
            article_repo=article_repo,
            settings=settings,
            relevance_scorer=relevance_scorer,
            admission_state=admission_state,
            canonical_hash=canonical_hash,
            canonical=canonical,
        )
        if action == "paused":
            break
        if action != "accept":
            continue

        row = _build_article_row(
            item=item,
            config=config,
            db_source_id=db_source_id,
            canonical=canonical,
            canonical_hash=canonical_hash,
            assessment=assessment,
            admission_enabled=admission_enabled,
        )
        if row is None:
            continue
        row_new, row_duplicate = _stage_row(
            row=row,
            canonical_hash=canonical_hash,
            batch_mode=batch_mode,
            queued_rows_by_hash=queued_rows_by_hash,
            article_repo=article_repo,
        )
        new_count += row_new
        duplicate_count += row_duplicate

    if batch_mode:
        batch_new, batch_duplicates = _upsert_article_rows(
            article_repo=article_repo,
            rows=list(queued_rows_by_hash.values()),
        )
        new_count += batch_new
        duplicate_count += batch_duplicates

    return new_count, duplicate_count, skipped_known_items, early_stop_hit
