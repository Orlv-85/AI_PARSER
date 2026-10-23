"""Private article archive: copy stored articles into archive documents and text versions; see
capture.md."""
from collections.abc import Iterable
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.archive import ArchiveRepo
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
