import ast
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.archive.capture import (
    ARCHIVE_MIN_TEXT_CHARS,
    ARTICLE_CONTENT_VERSION,
    archive_articles,
)
from app.storage.archive import ArchiveRepo
from app.storage.article_repo import ArticleRepo
from app.storage.daily_signals import DailySignalRepo
from app.storage.models_sql import ArchiveDocument, ArchiveText, Article, Base, Source

LONG = "Archived article body. " * 20
NOW = datetime.now(UTC)


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _article(session, key, *, content=LONG, days_old=1, source=None):
    row = Article(title=f"Title {key}", url=f"https://www.Example.com/{key}?utm=1",
                  url_canonical=f"https://www.example.com/{key}", url_canonical_hash=key * 8,
                  content=content, published_at=NOW - timedelta(days=days_old),
                  publication_day=(NOW - timedelta(days=days_old)).date(),
                  publication_status="verified", discovered_at=NOW - timedelta(days=days_old),
                  source_id=source.id if source else None)
    session.add(row)
    session.flush()
    return row


def _counts(session):
    return (session.scalar(select(func.count()).select_from(ArchiveDocument)),
            session.scalar(select(func.count()).select_from(ArchiveText)))


def test_sync_creates_document_and_content_version() -> None:
    session = _session()
    source = Source(source_key="example_rss", name="Example", type="rss", url="https://x/feed")
    session.add(source)
    session.flush()
    long_row = _article(session, "a", source=source)
    short_row = _article(session, "b", content="x" * (ARCHIVE_MIN_TEXT_CHARS - 1))

    assert archive_articles(session, [long_row, short_row]) == (2, 1)

    documents = {d.url_canonical_hash: d for d in session.scalars(select(ArchiveDocument))}
    long_doc, short_doc = documents["a" * 8], documents["b" * 8]
    assert (long_doc.state, long_doc.source_key, long_doc.host) == ("archived", "example_rss",
                                                                    "example.com")
    assert (long_doc.article_id, long_doc.title, long_doc.publication_status) == (
        long_row.id, "Title a", "verified")
    assert long_doc.publication_day == long_row.publication_day
    assert (short_doc.state, short_doc.source_key) == ("pending", None)
    version = session.scalars(select(ArchiveText)).one()
    assert version.document_id == long_doc.id
    assert (version.origin, version.extraction_version) == ("article_content",
                                                            ARTICLE_CONTENT_VERSION)
    assert (version.text, version.text_chars, version.issues) == (LONG, len(LONG), "[]")
    assert len(version.text_sha256) == 64


def test_sync_versions_only_on_text_change() -> None:
    session = _session()
    row = _article(session, "a")
    archive_articles(session, [row])
    assert archive_articles(session, [row]) == (1, 0)
    assert _counts(session) == (1, 1)

    row.content = LONG + " Updated."
    assert archive_articles(session, [row]) == (1, 1)
    texts = [v.text for v in session.scalars(select(ArchiveText).order_by(ArchiveText.id))]
    assert texts == [LONG, LONG + " Updated."]
    assert _counts(session) == (1, 2)


def test_recollected_article_reuses_document() -> None:
    session = _session()
    first = _article(session, "a", days_old=900)
    _article(session, "z", content=None)  # SQLite would reuse the highest freed rowid
    archive_articles(session, [first])
    document = session.scalars(select(ArchiveDocument)).one()
    first_seen, first_id = document.first_seen_at, first.id
    session.delete(first)
    session.flush()

    again = _article(session, "a", days_old=0)
    again.title = "New title"
    archive_articles(session, [again])

    assert _counts(session) == (1, 1)
    assert again.id != first_id
    assert (document.article_id, document.title) == (again.id, "New title")
    assert document.first_seen_at == first_seen


def test_prune_archives_rows_before_delete() -> None:
    session = _session()
    _article(session, "o", days_old=900)
    _article(session, "s", days_old=900, content=None)
    _article(session, "r", days_old=5)
    session.commit()

    assert ArticleRepo(session).prune_older_than(older_than_days=800) == (2, 0)
    session.commit()

    assert session.scalar(select(func.count()).select_from(Article)) == 1
    states = dict(session.execute(select(ArchiveDocument.url_canonical_hash,
                                         ArchiveDocument.state)).all())
    assert states == {"o" * 8: "archived", "s" * 8: "pending"}
    assert _counts(session) == (2, 1)


def test_prune_archive_rolls_back_with_delete() -> None:
    session = _session()
    _article(session, "o", days_old=900)
    session.commit()
    ArticleRepo(session).prune_older_than(older_than_days=800)
    session.rollback()
    assert session.scalar(select(func.count()).select_from(Article)) == 1
    assert _counts(session) == (0, 0)


def test_prune_dry_run_does_not_archive() -> None:
    session = _session()
    _article(session, "o", days_old=900)
    session.commit()
    assert ArticleRepo(session).count_older_than(older_than_days=800) == 1
    assert _counts(session) == (0, 0)


def test_prune_and_evidence_purge_keep_archive_rows() -> None:
    session = _session()
    old = _article(session, "o", days_old=900)
    old_id = old.id
    _article(session, "r", days_old=5)
    archive_articles(session, session.scalars(select(Article)).all())
    session.commit()
    assert _counts(session) == (2, 2)

    ArticleRepo(session).prune_older_than(older_than_days=800)
    session.commit()
    DailySignalRepo(session, comparable_from=date(2026, 1, 1)).purge_evidence(old_id)
    ArticleRepo(session).prune_older_than(older_than_days=1)
    session.commit()

    assert session.scalar(select(func.count()).select_from(Article)) == 0
    assert _counts(session) == (2, 2)


def test_archive_repo_purge_status_and_size() -> None:
    session = _session()
    rows = [_article(session, "a"), _article(session, "b", content=None)]
    rows[1].url = rows[1].url_canonical = "https://other.org/b"
    archive_articles(session, rows)
    repo = ArchiveRepo(session)
    assert repo.state_counts() == {"archived": 1, "pending": 1}
    assert repo.version_count() == 1
    assert repo.size_bytes() == len(LONG)

    assert repo.purge(host="www.example.com") == (1, 1)
    assert _counts(session) == (2, 1)
    assert repo.purge(host="example.com", apply=True) == (1, 1)
    assert _counts(session) == (1, 0)
    assert repo.purge(url="https://other.org/b", apply=True) == (1, 0)
    assert _counts(session) == (0, 0)


def test_archive_not_imported_by_web_or_mcp() -> None:
    web = Path(__file__).resolve().parents[2] / "src" / "app" / "web"
    banned = ("app.core.archive", "app.storage.archive")
    offenders = []
    for path in web.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                continue
            if any(n == b or n.startswith(b + ".") for n in names for b in banned):
                offenders.append(str(path))
    assert not offenders, offenders
