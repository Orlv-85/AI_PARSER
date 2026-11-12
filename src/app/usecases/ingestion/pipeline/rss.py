"""RSS path: persist the items of one fetched feed."""
from dataclasses import dataclass, field
from typing import Any

from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.ingestion.admission import (
    admission_cache_key,
    bounded_evidence,
    evidence_hash,
)
from app.core.ingestion.page_filter import (
    log_exclusion,
)
from app.storage.admission import (
    upsert_pending,
)
from app.usecases.ingestion.pipeline.models import SourceMetrics, SourceRun
from app.usecases.ingestion.pipeline.rows import (
    _candidate_payload,
    _item_exclusion_reason,
    _upsert_article_rows,
)
from app.usecases.ingestion.pipeline.screening import _assessed_row


def _accepted_items(items: list) -> list:
    accepted_items = []
    for item in items:
        reason = _item_exclusion_reason(item)
        if reason:
            log_exclusion(str(item.url), reason)
        else:
            accepted_items.append(item)
    return accepted_items


@dataclass
class _RssTally:
    new_count: int = 0
    duplicate_count: int = 0
    skipped_known_items: int = 0
    known_streak: int = 0
    early_stop_hit: bool = False
    queued_rows_by_hash: dict[str, dict[str, object]] = field(default_factory=dict)


def _queue_pending_candidates(run: SourceRun, *, items: list, use_known_skip: bool) -> None:
    settings = run.settings
    for item in items:
        identity_url = getattr(item, "ingestion_canonical_url", None) or str(item.url)
        canonical_hash = canonical_url_hash(identity_url)
        if use_known_skip and run.article_repo.exists_by_canonical_hash(canonical_hash):
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
            run.article_repo.session,
            key=key,
            url_canonical_hash=canonical_hash,
            source_id=run.db_source_id,
            payload=_candidate_payload(item, run.config),
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


def _count_known_item(tally: _RssTally, *, streak_stop: int) -> bool:
    """Count a stored item; True when the known streak says to stop (0 turns it off)."""
    tally.duplicate_count += 1
    tally.skipped_known_items += 1
    tally.known_streak += 1
    if 0 < streak_stop <= tally.known_streak:
        tally.early_stop_hit = True
        return True
    return False


def _stage_row(
    run: SourceRun, tally: _RssTally, row: dict[str, object], *, canonical_hash: str,
) -> None:
    """Store one row; batch mode only queues it, merging a repeat of the same URL."""
    if not run.settings.article_batch_upsert_enabled:
        _, is_new = run.article_repo.insert_article(row)
        if is_new:
            tally.new_count += 1
        else:
            tally.duplicate_count += 1
        return
    existing_row = tally.queued_rows_by_hash.get(canonical_hash)
    if existing_row is None:
        tally.queued_rows_by_hash[canonical_hash] = row
        return
    _merge_queued_row(existing_row, row)
    tally.duplicate_count += 1


def _flush_queued_rows(run: SourceRun, tally: _RssTally) -> None:
    if not run.settings.article_batch_upsert_enabled:
        return
    batch_new, batch_duplicates = _upsert_article_rows(
        article_repo=run.article_repo,
        rows=list(tally.queued_rows_by_hash.values()),
    )
    tally.new_count += batch_new
    tally.duplicate_count += batch_duplicates


def _process_item(
    run: SourceRun, tally: _RssTally, item: Any, *, use_known_skip: bool, streak_stop: int,
) -> bool:
    """Persist one feed item; True when the source loop stops (known streak or pause)."""
    identity_url = getattr(item, "ingestion_canonical_url", None) or str(item.url)
    canonical = canonicalize_url(identity_url)
    canonical_hash = canonical_url_hash(identity_url)
    if use_known_skip and run.article_repo.exists_by_canonical_hash(canonical_hash):
        return _count_known_item(tally, streak_stop=streak_stop)
    tally.known_streak = 0
    assessed: tuple[str, dict[str, object] | None] = _assessed_row(
        run, item, canonical=canonical, canonical_hash=canonical_hash,
    )
    action, row = assessed
    if row is not None:
        _stage_row(run, tally, row, canonical_hash=canonical_hash)
    return action == "paused"


def _process_fetched_source_items(
    run: SourceRun, items: list, metrics: SourceMetrics | None = None,
) -> tuple[int, int, int, bool]:
    tally = _RssTally()
    streak_stop = run.settings.rss_known_streak_stop if run.config.type == "rss" else 0
    use_known_skip = run.admission_enabled or streak_stop > 0
    items = _accepted_items(items)
    if run.admission_enabled:
        _queue_pending_candidates(run, items=items, use_known_skip=use_known_skip)

    for item in items:
        if metrics is not None:
            metrics.examined_items += 1
        if _process_item(run, tally, item, use_known_skip=use_known_skip, streak_stop=streak_stop):
            break

    _flush_queued_rows(run, tally)
    return (
        tally.new_count, tally.duplicate_count, tally.skipped_known_items, tally.early_stop_hit,
    )
