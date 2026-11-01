"""Original texts of a bulletin's linked articles, for the writer (spec 018, item 3).

The edge of src/app/core/bulletin/writer.py; behavior in src/app/core/bulletin/writer.md.
Read-only: nothing is written.
"""
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.bulletin.builder import Bulletin
from app.core.bulletin.writer import SourceText, all_stories
from app.core.canonicalize import canonical_url_hash
from app.storage.models_sql import ArchiveDocument, ArchiveText, Article

SOURCE_PAGE = "source_page"


def _archive_text(session: Session, url_hash: str) -> str | None:
    """Newest `source_page` text of the page, else the newest text of any origin."""
    text = session.scalar(
        select(ArchiveText.text)
        .join(ArchiveDocument, ArchiveDocument.id == ArchiveText.document_id)
        .where(ArchiveDocument.url_canonical_hash == url_hash)
        .order_by(case((ArchiveText.origin == SOURCE_PAGE, 0), else_=1),
                  ArchiveText.captured_at.desc(), ArchiveText.id.desc()).limit(1))
    return text or None


def load_sources(session: Session, bulletin: Bulletin) -> dict[str, SourceText]:
    """`SourceText` per link url of the bulletin's stories; a link without a stored article has
    an empty title and summary (the writer then uses the story title)."""
    found: dict[str, SourceText] = {}
    for story in all_stories(bulletin):
        for link in story.links:
            url = link["url"]
            digest = canonical_url_hash(url)
            article = session.scalar(select(Article).where(Article.url_canonical_hash == digest))
            found[url] = SourceText(
                url=url, title=article.title if article else "",
                summary=(article.summary or "") if article else "",
                text=_archive_text(session, digest))
    return found
