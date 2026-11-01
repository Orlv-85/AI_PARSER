"""World stream text download through the archive (spec 018, item 5, step W6).

Behavior in core/world/world.md. The top ranked representatives still `screened_in` become archive
documents (transient `Article`, as in `archive import-db`) and the archive's download step fetches
them; the stored text is the `TextSource` of step B. Lives outside core/world/ because it imports
storage.
"""
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.archive.capture import (
    ARCHIVE_CACHE_ROOT,
    DAILY_CACHE_ROOT,
    archive_articles,
    download_documents,
)
from app.core.canonicalize import canonicalize_url
from app.core.jev import CONTENT_LIMIT
from app.core.world.screen import WORLD_TOP_N
from app.core.world_screen import TextSource, rank_clusters
from app.storage.archive import (
    STATE_ARCHIVED,
    STATE_FAILED,
    STATE_GAVE_UP,
    STATE_PENDING,
    WORLD_SOURCE_KEY,
)
from app.storage.models_sql import ArchiveDocument, ArchiveText, Article, WorldCandidate
from app.storage.world import (
    STATE_ASSESSED,
    STATE_NO_TEXT,
    STATE_SCREENED_IN,
    STATE_TEXT_READY,
    WorldRepo,
)

TEXT_PREFIX = "text"
UNKNOWN_ISSUE = "unknown"


def archive_text_source(session: Session) -> TextSource:
    """Step B text seam: newest archive text of the candidate's page, cut to Jev's limit."""
    def read(candidate: WorldCandidate) -> str | None:
        text = session.scalar(
            select(ArchiveText.text)
            .join(ArchiveDocument, ArchiveDocument.id == ArchiveText.document_id)
            .where(ArchiveDocument.url_canonical_hash == candidate.url_canonical_hash)
            .order_by(ArchiveText.captured_at.desc(), ArchiveText.id.desc()).limit(1))
        return text[:CONTENT_LIMIT] if text else None
    return read


def _transient_article(candidate: WorldCandidate) -> Article:
    """An `Article` that is never added to a session: only `archive_articles` reads it."""
    return Article(
        title=candidate.title, url=candidate.url, url_canonical=canonicalize_url(candidate.url),
        url_canonical_hash=candidate.url_canonical_hash, content=None,
        published_at=candidate.published_at, discovered_at=candidate.first_seen_at)


def _new_summary(target: date, dry_run: bool) -> dict[str, Any]:
    return {"date": target.isoformat(), "dry_run": dry_run, "top": 0, "candidates": 0,
            "downloads": 0, "cache_reused": 0, "text_ready": 0, "no_text": 0, "reasons": {},
            "kept": 0, "outage": False}


def _documents(session: Session, reps: list[WorldCandidate]) -> dict[str, ArchiveDocument]:
    """Archive document per representative; only a hash without one gets a new, marked document
    (an existing one, maybe a real article, is read and never rewritten)."""
    def load() -> dict[str, ArchiveDocument]:
        return {d.url_canonical_hash: d for d in session.scalars(select(ArchiveDocument).where(
            ArchiveDocument.url_canonical_hash.in_([rep.url_canonical_hash for rep in reps])))}
    found = load()
    missing = [rep for rep in reps if rep.url_canonical_hash not in found]
    archive_articles(session, [_transient_article(rep) for rep in missing], {})
    for document in session.scalars(select(ArchiveDocument).where(
            ArchiveDocument.url_canonical_hash.in_([rep.url_canonical_hash for rep in missing]))):
        document.source_key = WORLD_SOURCE_KEY
    session.commit()
    return load()


def _settle(repo: WorldRepo, rep: WorldCandidate, document: ArchiveDocument,
            reasons: Counter[str]) -> str:
    """Move the candidate by what the archive recorded; returns the summary counter to raise."""
    if document.state == STATE_ARCHIVED:
        repo.transition(rep, STATE_TEXT_READY)
        return "text_ready"
    if document.state in (STATE_FAILED, STATE_GAVE_UP):
        issue = document.last_issue or UNKNOWN_ISSUE
        repo.transition(rep, STATE_NO_TEXT, error=f"{TEXT_PREFIX}: {issue}")
        reasons[issue] += 1
        return "no_text"
    return "kept"


def run_texts(  # pylint: disable=too-many-arguments,too-many-locals
    session: Session, target: date, *, top_n: int = WORLD_TOP_N, dry_run: bool = False,
    cache_root: Path = ARCHIVE_CACHE_ROOT, daily_cache_root: Path = DAILY_CACHE_ROOT,
    client_factory: Callable[[], httpx.AsyncClient] | None = None, host_interval: float = 1.0,
) -> dict[str, Any]:
    """Get text for the representatives of the top clusters that are still `screened_in`."""
    repo = WorldRepo(session)
    summary = _new_summary(target, dry_run)
    top = rank_clusters(repo.candidates_in_window(
        [STATE_SCREENED_IN, STATE_TEXT_READY, STATE_ASSESSED], target))[:top_n]
    reps = [item.rep for item in top if item.rep.state == STATE_SCREENED_IN]
    summary["top"], summary["candidates"] = len(top), len(reps)
    if dry_run:
        summary["would_download"] = len(reps)
        return summary
    if not reps:
        return summary
    documents = _documents(session, reps)
    due = [d.id for d in documents.values() if d.state == STATE_PENDING]
    if due:
        result = download_documents(
            session, due, cache_root=cache_root, daily_cache_root=daily_cache_root,
            client_factory=client_factory, host_interval=host_interval)
        summary["downloads"] = result["downloads"]
        summary["cache_reused"] = result["cache_reused"]
        summary["outage"] = result["outage"]
    reasons: Counter[str] = Counter()
    for rep in reps:
        document = documents[rep.url_canonical_hash]
        session.refresh(document)
        outcome = _settle(repo, rep, document, reasons)
        summary[outcome] += 1
        session.commit()
    summary["reasons"] = dict(reasons)
    return summary
