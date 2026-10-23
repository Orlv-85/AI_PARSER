"""Private article archive: copy stored articles into archive documents and text versions; see
capture.md."""
import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.observability.logging import log_event
from app.storage.archive import STATE_ARCHIVED, ArchiveRepo
from app.storage.models_sql import Article, Source

ARCHIVE_MIN_TEXT_CHARS = 300
ARCHIVE_LOOKBACK_DAYS = 7
ARCHIVE_RETRY_DELAYS = (timedelta(days=1), timedelta(days=3), timedelta(days=7))
ARCHIVE_MAX_DOWNLOADS = 200
ARCHIVE_MAX_PER_HOST = 20
ARCHIVE_DOWNLOAD_CONCURRENCY = 4
ARCHIVE_RAW_KEEP_DAYS = 14
ARCHIVE_SIZE_WARN_BYTES = 2 * 1024**3
ARTICLE_CONTENT_VERSION = "article-content-1"
ORIGIN_ARTICLE_CONTENT = "article_content"
CAPTURE_BATCH_SIZE = 200
STATUS_TOP_HOSTS = 10


def url_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def archive_articles(session: Session, articles: Iterable[Article]) -> tuple[int, int]:
    """Upsert one document per article and add its content as a version when long enough.

    Sync, no network, no commit (the caller owns the transaction). Returns (documents, new
    versions)."""
    rows = list(articles)
    source_ids = {row.source_id for row in rows if row.source_id is not None}
    source_keys: dict[int, str] = dict(session.execute(  # type: ignore[arg-type]
        select(Source.id, Source.source_key).where(Source.id.in_(source_ids))).all()
    ) if source_ids else {}
    repo = ArchiveRepo(session)
    added = 0
    for row in rows:
        document = repo.upsert_document(
            url_canonical_hash=row.url_canonical_hash, url=row.url,
            url_canonical=row.url_canonical,
            source_key=source_keys.get(row.source_id) if row.source_id is not None else None,
            host=url_host(row.url_canonical or row.url), title=row.title,
            published_at=row.published_at, publication_day=row.publication_day,
            publication_status=row.publication_status, article_id=row.id,
            first_seen_at=row.discovered_at)
        content = row.content or ""
        if len(content.strip()) >= ARCHIVE_MIN_TEXT_CHARS and repo.add_version(
                document, text=content, origin=ORIGIN_ARTICLE_CONTENT,
                extraction_version=ARTICLE_CONTENT_VERSION):
            added += 1
    return len(rows), added


def _coverage(states: list[tuple[datetime, str]]) -> tuple[int, int, float | None]:
    archived = sum(1 for _, state in states if state == STATE_ARCHIVED)
    pct = round(100.0 * archived / len(states), 1) if states else None
    return len(states), archived, pct


def capture(session: Session, *, scope_all: bool = False, no_download: bool = False,
            max_seconds: int | None = None, logger: logging.Logger | None = None,
            now: datetime | None = None) -> dict[str, Any]:
    """Sync the window (or every article with `scope_all`) into the archive and summarize.

    Downloads are not built yet (spec 016 phase 3): no network request is made, so `no_download`
    and `max_seconds` do not change the result."""
    del no_download, max_seconds
    started = now or datetime.now(UTC)
    since = None if scope_all else started - timedelta(days=ARCHIVE_LOOKBACK_DAYS)
    ids_stmt = select(Article.id).order_by(Article.id)
    if since is not None:
        ids_stmt = ids_stmt.where(Article.discovered_at >= since)
    ids = list(session.scalars(ids_stmt))
    synced = 0
    for start in range(0, len(ids), CAPTURE_BATCH_SIZE):
        chunk = ids[start:start + CAPTURE_BATCH_SIZE]
        rows = session.scalars(select(Article).where(Article.id.in_(chunk))).all()
        synced += archive_articles(session, rows)[0]
        session.commit()
        session.expunge_all()  # keep memory flat over a full seed
    repo = ArchiveRepo(session)
    documents, archived, pct = _coverage(repo.window_states(since))
    size = repo.size_bytes()
    summary: dict[str, Any] = {
        "window_days": None if scope_all else ARCHIVE_LOOKBACK_DAYS,
        "articles_synced": synced, "window_documents": documents, "window_archived": archived,
        "coverage_pct": pct, "new_versions": repo.new_versions_since(started),
        "archive_bytes": size, "archive_size_warning": size >= ARCHIVE_SIZE_WARN_BYTES,
    }
    if logger is not None:
        log_event(logger, event="archive_capture_finished", **summary)
    return summary


def status(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """Read-only archive totals, window coverage per first-seen day and hosts without text."""
    since = (now or datetime.now(UTC)) - timedelta(days=ARCHIVE_LOOKBACK_DAYS)
    repo = ArchiveRepo(session)
    states = repo.window_states(since)
    by_day: dict[str, list[tuple[datetime, str]]] = {}
    for seen, state in states:
        by_day.setdefault(seen.astimezone(UTC).date().isoformat(), []).append((seen, state))
    documents, archived, pct = _coverage(states)
    return {
        "states": repo.state_counts(), "versions": repo.version_count(),
        "archive_bytes": repo.size_bytes(),
        "window_days": ARCHIVE_LOOKBACK_DAYS, "window_documents": documents,
        "window_archived": archived, "coverage_pct": pct,
        "coverage_by_day": {day: dict(zip(("documents", "archived", "coverage_pct"),
                                          _coverage(rows), strict=True))
                            for day, rows in sorted(by_day.items())},
        "top_hosts_without_text": [{"host": host, "documents": count}
                                   for host, count in repo.hosts_without_text(STATUS_TOP_HOSTS)],
    }
