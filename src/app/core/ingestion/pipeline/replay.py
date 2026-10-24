"""Replay of pending admission candidates before a source's fresh fetch."""
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.ingestion.admission import (
    admission_cache_key,
    bounded_evidence,
    evidence_hash,
)
from app.core.ingestion.pipeline.html_links import _process_html_links_two_stage
from app.core.ingestion.pipeline.models import (
    PENDING_REPLAY_LIMIT,
    PENDING_REPLAY_MAX_AGE_DAYS,
    AdmissionState,
    SourceMetrics,
)
from app.core.ingestion.pipeline.rows import (
    _article_from_candidate,
    _item_exclusion_reason,
    _parse_dt,
)
from app.core.ingestion.pipeline.rss import _process_fetched_source_items
from app.core.ingestion.pipeline.screening import _html_placeholder_key
from app.core.jev import JevRelevanceScorer
from app.core.models import Article as CoreArticle
from app.storage.admission import (
    get_cached_decision,
    list_pending,
    settle_pending,
)
from app.storage.article_repo import ArticleRepo


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


def _replay_pending_for_source(  # pylint: disable=too-many-branches
    *, session: Session, config: SourceConfig, db_source_id: int,
    article_repo: ArticleRepo, settings: Settings,
    relevance_scorer: JevRelevanceScorer | None, admission_state: AdmissionState,
    metrics: SourceMetrics,
) -> int:
    pending = _take_fresh_pending(session, db_source_id)
    bodies: list[tuple[Any, CoreArticle]] = []
    links: list[Any] = []
    for entry in pending:
        candidate = json.loads(entry.payload).get("candidate")
        if candidate.get("kind") == "html_link":
            links.append(entry)
        elif candidate.get("kind") == "article":
            bodies.append((entry, _article_from_candidate(candidate, config.id)))
        else:
            raise ValueError("Invalid stored admission candidate kind")

    if bodies:
        items = [item for _, item in bodies]
        new, duplicates, skipped, _ = _process_fetched_source_items(
            items=items, config=config, db_source_id=db_source_id,
            article_repo=article_repo, settings=settings,
            relevance_scorer=relevance_scorer, admission_state=admission_state,
        )
        metrics.fetched_items += len(items)
        metrics.new_items += new
        metrics.duplicate_items += duplicates
        metrics.skipped_known_items += skipped
        for entry, item in bodies:
            current_key = admission_cache_key(
                url_canonical_hash=entry.url_canonical_hash,
                evidence_hash=evidence_hash(bounded_evidence(item)),
                model=settings.jev_model,
                policy_version=settings.semantic_admission_policy_version,
                prompt_version=settings.semantic_admission_prompt_version,
            )
            current = get_cached_decision(session, current_key)
            if _item_exclusion_reason(item) or article_repo.exists_by_canonical_hash(
                entry.url_canonical_hash
            ):
                if entry.provider_status == "pending":
                    settle_pending(session, key=entry.key)
            elif current is not None and current_key != entry.key:
                settle_pending(session, key=entry.key)

    replayed = len(bodies)
    if links and not admission_state.paused:
        urls = [str(json.loads(entry.payload)["candidate"]["url"]) for entry in links]
        fetched, new, duplicates, skipped, _ = _process_html_links_two_stage(
            links=urls, config=config, db_source_id=db_source_id,
            article_repo=article_repo, settings=settings,
            relevance_scorer=relevance_scorer, admission_state=admission_state,
        )
        replayed += len(links)
        metrics.fetched_items += fetched
        metrics.new_items += new
        metrics.duplicate_items += duplicates
        metrics.skipped_known_items += skipped
        metrics.acquisition_stopped = admission_state.paused
        for entry in links:
            current_key = _html_placeholder_key(settings, entry.url_canonical_hash)
            current = get_cached_decision(session, current_key)
            if current_key != entry.key and current is not None:
                settle_pending(session, key=entry.key)
    return replayed
