"""Replay of pending admission candidates before a source's fresh fetch."""
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy.orm import Session

from app.core.ingestion.admission import (
    admission_cache_key,
    bounded_evidence,
    evidence_hash,
)
from app.core.models import Article as CoreArticle
from app.storage.admission import (
    get_cached_decision,
    list_pending,
    settle_pending,
)
from app.usecases.ingestion.pipeline.html_links import _process_html_links_two_stage
from app.usecases.ingestion.pipeline.models import (
    PENDING_REPLAY_LIMIT,
    PENDING_REPLAY_MAX_AGE_DAYS,
    AdmissionState,
    SourceMetrics,
    SourceRun,
)
from app.usecases.ingestion.pipeline.rows import (
    _article_from_candidate,
    _item_exclusion_reason,
    _parse_dt,
)
from app.usecases.ingestion.pipeline.rss import _process_fetched_source_items
from app.usecases.ingestion.pipeline.screening import _html_placeholder_key


def _is_stale_pending(candidate: dict[str, object], cutoff: datetime) -> bool:
    if candidate.get("kind") != "article":
        return False
    published: datetime | None = _parse_dt(candidate.get("published_at"))
    if published is None:
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    return published < cutoff


def _take_fresh_pending(session: Session, db_source_id: int) -> list[Any]:
    """Settle archive-old pending bodies, then return up to the replay limit of the rest."""
    cutoff = datetime.now(UTC) - timedelta(days=PENDING_REPLAY_MAX_AGE_DAYS)
    while True:
        pending: list[Any] = list_pending(
            session, source_id=db_source_id, limit=PENDING_REPLAY_LIMIT,
        )
        stale = 0
        for entry in pending:
            candidate = json.loads(entry.payload).get("candidate")
            if not isinstance(candidate, dict):
                raise ValueError("Invalid stored admission candidate")
            if _is_stale_pending(candidate, cutoff):
                settle_pending(session, key=entry.key, reason="stale_pending")
                stale += 1
        if not stale:
            return pending


def _split_pending(pending: list[Any],
                   source_id: str) -> tuple[list[tuple[Any, CoreArticle]], list[Any]]:
    """Stored candidates as (entry, article) bodies and html link entries."""
    bodies: list[tuple[Any, CoreArticle]] = []
    links: list[Any] = []
    for entry in pending:
        candidate = json.loads(entry.payload).get("candidate")
        if candidate.get("kind") == "html_link":
            links.append(entry)
        elif candidate.get("kind") == "article":
            bodies.append((entry, _article_from_candidate(candidate, source_id)))
        else:
            raise ValueError("Invalid stored admission candidate kind")
    return bodies, links


def _add_counts(metrics: SourceMetrics, fetched: int, new: int, duplicates: int,
                skipped: int) -> None:
    metrics.fetched_items += fetched
    metrics.new_items += new
    metrics.duplicate_items += duplicates
    metrics.skipped_known_items += skipped


def _replay_bodies(session: Session, run: SourceRun, metrics: SourceMetrics,
                   bodies: list[tuple[Any, CoreArticle]]) -> None:
    """Process stored article bodies; settle entries that are now excluded, known or re-keyed."""
    settings = run.settings
    items = [item for _, item in bodies]
    new, duplicates, skipped, _ = _process_fetched_source_items(run, items)
    _add_counts(metrics, len(items), new, duplicates, skipped)
    for entry, item in bodies:
        current_key = admission_cache_key(
            url_canonical_hash=entry.url_canonical_hash,
            evidence_hash=evidence_hash(bounded_evidence(item)),
            model=settings.jev_model,
            policy_version=settings.semantic_admission_policy_version,
            prompt_version=settings.semantic_admission_prompt_version,
        )
        current = get_cached_decision(session, current_key)
        if _item_exclusion_reason(item) or run.article_repo.exists_by_canonical_hash(
            entry.url_canonical_hash
        ):
            if entry.provider_status == "pending":
                settle_pending(session, key=entry.key)
        elif current is not None and current_key != entry.key:
            settle_pending(session, key=entry.key)


def _replay_links(session: Session, run: SourceRun, metrics: SourceMetrics,
                  links: list[Any]) -> None:
    """Fetch stored html links again; settle entries whose placeholder key changed."""
    admission_state = cast(AdmissionState, run.admission_state)
    urls = [str(json.loads(entry.payload)["candidate"]["url"]) for entry in links]
    fetched, new, duplicates, skipped, _ = _process_html_links_two_stage(run, urls)
    _add_counts(metrics, fetched, new, duplicates, skipped)
    metrics.acquisition_stopped = admission_state.paused
    for entry in links:
        current_key = _html_placeholder_key(run.settings, entry.url_canonical_hash)
        current = get_cached_decision(session, current_key)
        if current_key != entry.key and current is not None:
            settle_pending(session, key=entry.key)


def _replay_pending_for_source(session: Session, run: SourceRun, metrics: SourceMetrics) -> int:
    """Replay the source's pending candidates; `run` carries the admission state."""
    admission_state = cast(AdmissionState, run.admission_state)
    bodies, links = _split_pending(_take_fresh_pending(session, run.db_source_id), run.config.id)
    if bodies:
        _replay_bodies(session, run, metrics, bodies)
    replayed = len(bodies)
    if links and not admission_state.paused:
        _replay_links(session, run, metrics, links)
        replayed += len(links)
    return replayed
