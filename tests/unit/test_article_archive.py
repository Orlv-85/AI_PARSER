import ast
import hashlib
import json
import logging
import socket
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from app.cli import main as cli_main
from app.core.archive import capture as capture_module
from app.core.archive.capture import (
    ARCHIVE_MIN_TEXT_CHARS,
    ARTICLE_CONTENT_VERSION,
    archive_articles,
    capture,
    status,
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


def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network request in archive capture")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_capture_window_and_seed_make_no_requests(tmp_path, monkeypatch) -> None:
    _no_network(monkeypatch)
    monkeypatch.setattr(capture_module, "CAPTURE_BATCH_SIZE", 2)
    session = _session()
    for key, days in (("a", 1), ("b", 2), ("c", 3), ("o", 30)):
        _article(session, key, days_old=days)
    _article(session, "p", days_old=1, content=None)  # due, but --no-download
    session.commit()

    summary = capture(session, no_download=True, max_seconds=1, cache_root=tmp_path / "a",
                      daily_cache_root=tmp_path / "d")
    assert (summary["window_days"], summary["articles_synced"]) == (7, 4)
    assert (summary["downloads"], summary["cache_reused"]) == (0, 0)
    assert _counts(session) == (4, 3)
    assert not (tmp_path / "a").exists()

    summary = capture(session, scope_all=True, no_download=True)
    assert (summary["window_days"], summary["articles_synced"]) == (None, 5)
    assert summary["new_versions"] == {"article_content": 1}
    assert _counts(session) == (5, 4)


PAGE = ("<html><head><title>Page</title></head><body><article><h1>Archived page</h1>"
        + "An editorial article about AI models and research. " * 30 + "</article></body></html>")


def _site(request):
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    if "other.org" in str(request.url):
        return httpx.Response(404, text="<html><title>Not found</title></html>",
                              headers={"Content-Type": "text/html"})
    return httpx.Response(200, text=PAGE, headers={"Content-Type": "text/html"})


def test_capture_summary_reports_coverage(tmp_path, caplog) -> None:
    session = _session()
    _article(session, "a", days_old=1)
    _article(session, "b", days_old=1, content=None)
    other = _article(session, "c", days_old=2, content=None)
    other.url = other.url_canonical = "https://other.org/c"
    _article(session, "o", days_old=30, content=None)
    session.commit()

    logger = logging.getLogger("test_archive_capture")
    with caplog.at_level(logging.INFO, logger="test_archive_capture"):
        summary = capture(session, logger=logger, cache_root=tmp_path / "archive",
                          daily_cache_root=tmp_path / "daily", host_interval=0,
                          client_factory=lambda: httpx.AsyncClient(
                              transport=httpx.MockTransport(_site)))
    texts = sum(len(t) for t in session.scalars(select(ArchiveText.text)))
    assert summary == {
        "window_days": 7, "articles_synced": 3, "window_documents": 3, "window_archived": 2,
        "coverage_pct": 66.7, "new_versions": {"article_content": 1, "source_page": 1},
        "cache_reused": 0, "downloads": 2, "failed": {"http_404": 1}, "gave_up": 1,
        "skipped_cap": 0, "skipped_time": 0, "outage": False, "outage_kept": 0,
        "raw_dirs_deleted": 0, "archive_bytes": texts, "archive_size_warning": False}
    record = next(r for r in caplog.records if r.getMessage() == "archive_capture_finished")
    assert record.event_fields == summary

    report = status(session)
    assert report["states"] == {"archived": 2, "gave_up": 1}
    assert (report["versions"], report["window_documents"], report["coverage_pct"]) == (2, 3, 66.7)
    day = (NOW - timedelta(days=1)).date().isoformat()
    assert report["coverage_by_day"][day] == {"documents": 2, "archived": 2,
                                              "coverage_pct": 100.0}
    assert report["top_hosts_without_text"] == [{"host": "other.org", "documents": 1}]
    assert _counts(session) == (3, 2)


def test_archive_purge_dry_run_and_apply(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'archive.db'}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        rows = [_article(session, "a"), _article(session, "b")]
        rows[1].url = rows[1].url_canonical = "https://other.org/b"
        archive_articles(session, rows)
        session.commit()
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "SessionLocal", factory)
    runner = CliRunner()

    def run(*args):
        return runner.invoke(cli_main.app, ["archive", "purge", *args])

    def counts():
        with factory() as session:
            return _counts(session)

    for bad in ([], ["--host", "example.com", "--source", "x"]):
        result = run(*bad)
        assert result.exit_code == 2
        assert "exactly one of --url, --source, --host" in result.output
    result = run("--host", "example.com")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"state": "dry_run", "documents": 1, "versions": 1}
    assert counts() == (2, 2)
    result = run("--host", "example.com", "--apply")
    assert json.loads(result.stdout) == {"state": "deleted", "documents": 1, "versions": 1}
    assert counts() == (1, 1)
    result = run("--url", "https://other.org/b", "--apply")
    assert json.loads(result.stdout) == {"state": "deleted", "documents": 1, "versions": 1}
    assert counts() == (0, 0)


def _file_db(path):
    engine = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _import_dbs(tmp_path):
    """Source (dump): a, b, c with source s_dump; target: article a, archived b, no c."""
    source_path = tmp_path / "source.db"
    with _file_db(source_path)() as session:
        session.add(Source(source_key="unused", name="U", type="rss", url="https://u/feed"))
        session.flush()
        dump_source = Source(source_key="s_dump", name="Dump", type="rss", url="https://d/feed")
        session.add(dump_source)
        session.flush()
        for key in ("a", "b", "c"):
            _article(session, key, days_old=2900, source=dump_source)
        _article(session, "d", days_old=2900, content="short")
        session.commit()
    target = _file_db(tmp_path / "target.db")
    with target() as session:
        _article(session, "a")
        archive_articles(session, [_article(session, "b")])
        session.delete(session.scalars(select(Article).where(
            Article.url_canonical_hash == "b" * 8)).one())
        session.commit()
    return source_path, target


def _run_import(monkeypatch, target, *args):
    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "SessionLocal", target)
    return CliRunner().invoke(cli_main.app, ["archive", "import-db", *args])


def test_import_db_archives_only_missing_hashes(tmp_path, monkeypatch) -> None:
    _no_network(monkeypatch)
    source_path, target = _import_dbs(tmp_path)
    result = _run_import(monkeypatch, target, "--source-url", f"sqlite:///{source_path}",
                         "--apply")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"source_articles": 4, "selected": 2,
                                         "selected_with_text": 1, "documents": 2,
                                         "new_versions": 1}
    with target() as session:
        documents = {d.url_canonical_hash: d for d in session.scalars(select(ArchiveDocument))}
        assert set(documents) == {"b" * 8, "c" * 8, "d" * 8}
        imported = documents["c" * 8]
        assert (imported.source_key, imported.state, imported.title) == ("s_dump", "archived",
                                                                         "Title c")
        assert documents["d" * 8].state == "pending"
        texts = session.scalars(select(ArchiveText).where(
            ArchiveText.document_id == imported.id)).all()
        assert [t.text for t in texts] == [LONG]
        assert session.scalar(select(func.count()).select_from(Article)) == 1
    again = _run_import(monkeypatch, target, "--source-url", f"sqlite:///{source_path}",
                        "--apply")
    assert json.loads(again.stdout)["selected"] == 0


def test_import_db_dry_run_writes_nothing(tmp_path, monkeypatch) -> None:
    source_path, target = _import_dbs(tmp_path)
    before = hashlib.sha256(source_path.read_bytes()).hexdigest()
    result = _run_import(monkeypatch, target, "--source-url", f"sqlite:///{source_path}")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"source_articles": 4, "selected": 2,
                                         "selected_with_text": 1}
    with target() as session:
        assert _counts(session) == (1, 1)
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == before
    missing = tmp_path / "missing.db"
    result = _run_import(monkeypatch, target, "--source-url", f"sqlite:///{missing}")
    assert result.exit_code == 2
    assert "source database file not found" in result.output
    assert not missing.exists()
