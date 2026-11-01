import asyncio
import json
import os
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.archive import capture as capture_module
from app.core.archive.capture import (
    ARCHIVE_MAX_PER_HOST,
    ARCHIVE_RAW_KEEP_DAYS,
    ARCHIVE_RETRY_DELAYS,
    capture,
    dedupe_page_cache,
)
from app.storage.archive import WORLD_SOURCE_KEY, ArchiveRepo
from app.storage.article_evidence_cache import EXTRACTION_VERSION, PageCache, url_key
from app.storage.models_sql import ArchiveDocument, ArchiveText, Article, Base

NOW = datetime.now(UTC)
PAGE = ("<html><head><title>Page</title></head><body><article><h1>Archived page</h1>"
        + "An editorial article about AI models and research. " * 30 + "</article></body></html>")


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _article(session, key, host="example.com", days_old=1):
    url = f"https://{host}/{key}"
    session.add(Article(title=f"Title {key}", url=url, url_canonical=url,
                        url_canonical_hash=f"{host}/{key}", content=None,
                        published_at=NOW - timedelta(days=days_old),
                        discovered_at=NOW - timedelta(days=days_old)))
    session.commit()
    return url


def _transport(routes, calls):
    """routes: url -> (status, body) or an exception class; robots.txt answers 404."""
    def handle(request):
        url = str(request.url)
        calls.append(url)
        if request.url.path == "/robots.txt":
            status, body = routes.get(url, (404, ""))
            return httpx.Response(status, text=body)
        answer = routes.get(url, (200, PAGE))
        if isinstance(answer, type):
            raise answer("failure", request=request)
        status, body = answer
        return httpx.Response(status, text=body, headers={"Content-Type": "text/html"})
    return handle


def _capture(session, tmp_path, routes=None, calls=None, **kwargs):
    calls = [] if calls is None else calls
    transport = httpx.MockTransport(_transport(routes or {}, calls))
    options = {"cache_root": tmp_path / "archive", "daily_cache_root": tmp_path / "daily",
               "host_interval": 0, "client_factory": lambda: httpx.AsyncClient(transport=transport),
               **kwargs}
    return capture(session, **options)


def _document(session, url):
    session.expire_all()
    return session.scalars(select(ArchiveDocument).where(ArchiveDocument.url == url)).one()


def _pages(calls):
    return [c for c in calls if not c.endswith("/robots.txt")]


def test_capture_reuses_daily_publish_page(tmp_path) -> None:
    session = _session()
    url = _article(session, "a")
    daily = PageCache(tmp_path / "daily")
    calls: list[str] = []

    async def seed():
        async with httpx.AsyncClient(transport=httpx.MockTransport(_transport({}, []))) as client:
            await capture_module.SourcePageDownloader(daily, client, host_interval=0,
                                                      respect_robots=False).fetch_one(url)
    asyncio.run(seed())
    before = {p.relative_to(tmp_path): p.stat().st_mtime_ns
              for p in (tmp_path / "daily").rglob("*")}

    summary = _capture(session, tmp_path, calls=calls)

    assert not calls, calls
    assert (summary["cache_reused"], summary["downloads"]) == (1, 0)
    document = _document(session, url)
    assert (document.state, document.attempts) == ("archived", 0)
    version = session.scalars(select(ArchiveText)).one()
    assert (version.origin, version.extraction_version, version.http_status) == (
        "source_page", EXTRACTION_VERSION, 200)
    assert {p.relative_to(tmp_path): p.stat().st_mtime_ns
            for p in (tmp_path / "daily").rglob("*")} == before


def test_capture_downloads_and_archives_page(tmp_path) -> None:
    session = _session()
    url = _article(session, "a")
    calls: list[str] = []
    summary = _capture(session, tmp_path, calls=calls)

    assert _pages(calls) == [url]
    assert "https://example.com/robots.txt" in calls
    assert (summary["downloads"], summary["new_versions"]) == (1, {"source_page": 1})
    document = _document(session, url)
    assert (document.state, document.attempts, document.last_issue) == ("archived", 1, None)
    version = session.scalars(select(ArchiveText)).one()
    assert (version.final_url, version.http_status, version.issues) == (url, 200, "[]")
    assert "editorial article about AI models" in version.text
    again: list[str] = []
    _capture(session, tmp_path, calls=again)
    assert not again, again


def test_capture_gives_up_on_permanent_issues(tmp_path) -> None:
    session = _session()
    gone = _article(session, "gone")
    removed = _article(session, "removed")
    blocked = _article(session, "x", host="blocked.org")
    down = _article(session, "y", host="down.org")
    routes = {gone: (404, "<html><title>Not found</title></html>"),
              removed: (410, "<html><title>Gone</title></html>"),
              "https://blocked.org/robots.txt": (200, "User-agent: *\nDisallow: /"),
              "https://down.org/robots.txt": (500, "")}
    summary = _capture(session, tmp_path, routes)

    assert [(_document(session, u).state, _document(session, u).last_issue)
            for u in (gone, removed, blocked, down)] == [
        ("gave_up", "http_404"), ("gave_up", "http_410"),
        ("gave_up", "robots_disallowed_or_unavailable"), ("failed", "robots_unavailable")]
    assert _document(session, gone).next_attempt_at is None
    assert summary["gave_up"] == 3


def test_capture_retry_schedule_then_gives_up(tmp_path) -> None:
    session = _session()
    url = _article(session, "a", days_old=0)
    routes = {url: (403, "<html><title>Forbidden</title></html>")}
    now = NOW
    for attempt, delay in enumerate(ARCHIVE_RETRY_DELAYS, start=1):
        calls: list[str] = []
        _capture(session, tmp_path, routes, calls, now=now)
        document = _document(session, url)
        assert (document.state, document.attempts, document.last_issue) == (
            "failed", attempt, "http_403")
        assert document.next_attempt_at == now + delay
        early: list[str] = []
        _capture(session, tmp_path, routes, early, now=now + delay - timedelta(minutes=1))
        assert _pages(early) == []
        now += delay
    calls = []
    _capture(session, tmp_path, routes, calls, now=now)
    assert _pages(calls) == [url]
    document = _document(session, url)
    assert (document.state, document.attempts, document.next_attempt_at) == ("gave_up", 4, None)
    calls = []
    _capture(session, tmp_path, routes, calls, now=now + timedelta(days=30), scope_all=True)
    assert not _pages(calls)


def test_capture_retry_clears_only_archive_cache(tmp_path) -> None:
    session = _session()
    url = _article(session, "a")
    daily_dir = tmp_path / "daily" / "pages" / url_key(url)
    daily_dir.mkdir(parents=True)
    (daily_dir / "attempt.json").write_text(json.dumps({"state": "failed", "issues": ["http_403"]}))
    calls: list[str] = []
    _capture(session, tmp_path, {url: (403, "<html></html>")}, calls, now=NOW)
    archive_dir = tmp_path / "archive" / "pages" / url_key(url)
    first = json.loads((archive_dir / "attempt.json").read_text())

    calls = []
    _capture(session, tmp_path, {}, calls, now=NOW + ARCHIVE_RETRY_DELAYS[0])
    assert _pages(calls) == [url]
    assert json.loads((archive_dir / "attempt.json").read_text())["started_at"] != \
        first["started_at"]
    assert _document(session, url).state == "archived"
    assert json.loads((daily_dir / "attempt.json").read_text()) == {
        "state": "failed", "issues": ["http_403"]}


def test_capture_resumes_attempt_of_killed_run(tmp_path) -> None:
    session = _session()
    url = _article(session, "a")
    seeded: list[str] = []
    _capture(session, tmp_path, calls=seeded, no_download=True)
    cache = PageCache(tmp_path / "archive")

    async def download():
        transport = httpx.MockTransport(_transport({}, []))
        async with httpx.AsyncClient(transport=transport) as client:
            await capture_module.SourcePageDownloader(cache, client, host_interval=0,
                                                      respect_robots=False).fetch_one(url)
    asyncio.run(download())
    calls: list[str] = []
    _capture(session, tmp_path, calls=calls)
    assert not calls, calls
    document = _document(session, url)
    assert (document.state, document.attempts) == ("archived", 1)


def test_capture_respects_caps_and_time(tmp_path, monkeypatch) -> None:
    session = _session()
    for i in range(ARCHIVE_MAX_PER_HOST + 2):
        _article(session, f"a{i}", host="busy.com")
    for i in range(3):
        _article(session, f"b{i}", host=f"h{i}.org")
    monkeypatch.setattr(capture_module, "ARCHIVE_MAX_DOWNLOADS", ARCHIVE_MAX_PER_HOST + 1)
    calls: list[str] = []
    summary = _capture(session, tmp_path, calls=calls)
    pages = _pages(calls)
    assert len(pages) == ARCHIVE_MAX_PER_HOST + 1
    assert sum("busy.com" in p for p in pages) <= ARCHIVE_MAX_PER_HOST
    assert {p for p in pages if "busy.com" not in p} >= {"https://h0.org/b0"}
    assert (summary["downloads"], summary["skipped_cap"]) == (ARCHIVE_MAX_PER_HOST + 1, 4)

    ticks = iter([0.0, 0.0, 1.0] + [99.0] * 100)
    calls = []
    summary = _capture(session, tmp_path, calls=calls, max_seconds=1,
                       clock=lambda: next(ticks))
    assert summary["downloads"] == 1
    assert summary["skipped_time"] == 3
    states = {d.state for d in session.scalars(select(ArchiveDocument))}
    assert states == {"archived", "pending"}


def test_capture_outage_keeps_attempts(tmp_path) -> None:
    session = _session()
    urls = [_article(session, "a", host=f"host{i}.org") for i in range(12)]

    def refuse(request):
        raise httpx.ConnectError("DNS unavailable", request=request)
    summary = capture(session, cache_root=tmp_path / "archive",
                      daily_cache_root=tmp_path / "daily", host_interval=0,
                      client_factory=lambda: httpx.AsyncClient(
                          transport=httpx.MockTransport(refuse)))
    assert summary["outage"] is True
    assert summary["outage_kept"] == summary["downloads"] > 0
    assert summary["failed"] == {} and summary["gave_up"] == 0
    for url in urls:
        document = _document(session, url)
        assert (document.state, document.attempts, document.next_attempt_at) == (
            "pending", 0, None)
    assert not any((tmp_path / "archive" / "pages").iterdir())


def test_capture_timeouts_are_an_outage(tmp_path) -> None:
    session = _session()
    urls = [_article(session, "a", host=f"host{i}.org") for i in range(12)]

    def time_out(request):
        raise httpx.ConnectTimeout("network down", request=request)
    summary = capture(session, cache_root=tmp_path / "archive",
                      daily_cache_root=tmp_path / "daily", host_interval=0,
                      client_factory=lambda: httpx.AsyncClient(
                          transport=httpx.MockTransport(time_out)))
    assert summary["outage"] is True
    assert summary["outage_kept"] == summary["downloads"] > 0
    assert summary["failed"] == {} and summary["gave_up"] == 0
    for url in urls:
        document = _document(session, url)
        assert (document.state, document.attempts, document.next_attempt_at) == (
            "pending", 0, None)


def test_capture_few_timeouts_are_per_document(tmp_path) -> None:
    session = _session()
    url = _article(session, "slow", host="slow.org")
    other = _article(session, "fine", host="fine.org")
    summary = _capture(session, tmp_path, {url: httpx.ReadTimeout})
    assert summary["outage"] is False
    assert summary["failed"] == {"ReadTimeout": 1}
    assert _document(session, url).attempts == 1
    assert _document(session, other).state == "archived"


def test_capture_deletes_old_raw_pages(tmp_path) -> None:
    session = _session()
    old_url = _article(session, "old")
    _capture(session, tmp_path)
    pages = tmp_path / "archive" / "pages"
    old_dir = pages / url_key(old_url)
    assert old_dir.is_dir()
    stale = time.time() - (ARCHIVE_RAW_KEEP_DAYS + 1) * 86400
    for path in [old_dir, *old_dir.iterdir()]:
        os.utime(path, (stale, stale))
    robots = next((tmp_path / "archive" / "robots").glob("*.json"))
    os.utime(robots, (stale, stale))
    new_url = _article(session, "new")

    summary = _capture(session, tmp_path)

    assert summary["raw_dirs_deleted"] == 1
    assert not old_dir.exists()
    assert (pages / url_key(new_url)).is_dir()
    assert _document(session, old_url).state == "archived"


def test_dedupe_page_cache_dry_run_then_apply(tmp_path) -> None:
    archive, daily = tmp_path / "archive", tmp_path / "daily"
    rebuildable = archive / "pages" / "a"
    no_response = daily / "pages" / "b"
    clean = daily / "pages" / "c"
    for directory in (rebuildable, no_response, clean):
        directory.mkdir(parents=True)
        (directory / "body.bin").write_bytes(b"x" * 10)
    (rebuildable / "response.json").write_text("{}")
    (rebuildable / "page.html").write_bytes(b"x" * 10)
    (no_response / "page.html").write_bytes(b"x" * 10)

    dry = dedupe_page_cache([archive, daily, tmp_path / "missing"])
    assert dry == {"dirs": 1, "files": 1, "bytes": 10}
    assert (rebuildable / "page.html").exists()

    applied = dedupe_page_cache([archive, daily], apply=True)
    assert applied == dry
    assert not (rebuildable / "page.html").exists()
    assert (rebuildable / "body.bin").exists()
    assert (no_response / "page.html").exists()
    assert dedupe_page_cache([archive, daily], apply=True)["files"] == 0


def test_download_documents_touches_only_given_ids(tmp_path) -> None:
    session = _session()
    chosen = _article(session, "chosen")
    other = _article(session, "other")
    calls: list[str] = []
    transport = httpx.MockTransport(_transport({}, calls))
    ids = [_document_after_sync(session, chosen)]

    summary = capture_module.download_documents(
        session, ids, cache_root=tmp_path / "archive", daily_cache_root=tmp_path / "daily",
        client_factory=lambda: httpx.AsyncClient(transport=transport), host_interval=0)

    assert _pages(calls) == [chosen]
    assert summary["downloads"] == 1
    assert _document(session, chosen).state == "archived"
    assert _document(session, other).state == "pending"


def _document_after_sync(session, url) -> int:
    rows = session.scalars(select(Article)).all()
    capture_module.archive_articles(session, rows)
    session.commit()
    return int(_document(session, url).id)


def _world_document(session, key="w"):
    url = f"https://world.example.org/{key}"
    return ArchiveRepo(session).upsert_document(
        url_canonical_hash=f"world/{key}", url=url, url_canonical=url,
        source_key=WORLD_SOURCE_KEY, host="world.example.org", title="World", published_at=None,
        publication_day=None, publication_status=None, article_id=None, first_seen_at=NOW)


def test_archive_coverage_skips_world_documents() -> None:
    session = _session()
    _world_document(session)
    _article(session, "real")
    capture_module.archive_articles(session, session.scalars(select(Article)).all())
    states = ArchiveRepo(session).window_states(None)
    assert len(states) == 1


def test_archive_due_skips_world_documents() -> None:
    session = _session()
    document = _world_document(session)
    repo = ArchiveRepo(session)
    assert not repo.due(None, NOW)
    assert repo.due(None, NOW, ids=[document.id]) == [document]


def test_archive_status_skips_world_documents() -> None:
    session = _session()
    _world_document(session)
    _article(session, "real")
    capture_module.archive_articles(session, session.scalars(select(Article)).all())
    report = capture_module.status(session, now=NOW)
    assert report["states"] == {"pending": 1}
    assert report["top_hosts_without_text"] == [{"host": "example.com", "documents": 1}]


def test_real_article_takes_over_a_world_document() -> None:
    session = _session()
    _world_document(session)
    url = "https://world.example.org/w"
    real = Article(id=7, source_id=1, title="Real title", url=url, url_canonical=url,
                   url_canonical_hash="world/w", content=None, discovered_at=NOW)
    capture_module.archive_articles(session, [real], {1: "real-source"})
    document = session.scalars(select(ArchiveDocument)).one()
    assert (document.source_key, document.article_id, document.title) == (
        "real-source", 7, "Real title")
    assert ArchiveRepo(session).due(None, NOW) == [document]
    assert len(ArchiveRepo(session).window_states(None)) == 1
