"""Private article archive: copy stored articles into archive documents and text versions; see
capture.md."""
import asyncio
import hashlib
import json
import logging
import shutil
import time
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple, NotRequired, TypedDict
from urllib.parse import urlsplit

import httpx
from sqlalchemy import Connection, create_engine, inspect, make_url, select
from sqlalchemy.orm import Session

from app.observability.logging import log_event
from app.storage.archive import (
    STATE_ARCHIVED,
    STATE_PENDING,
    ArchiveRepo,
    DocumentMeta,
    TextVersion,
)
from app.storage.article_evidence_cache import (
    EXTRACTION_VERSION,
    DownloadLimits,
    PageCache,
    SourcePageDownloader,
    make_http_client,
    url_key,
)
from app.storage.article_repo import ArticleRepo
from app.storage.models_sql import ArchiveDocument, Article, Source

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
ORIGIN_SOURCE_PAGE = "source_page"
CAPTURE_BATCH_SIZE = 200
STATUS_TOP_HOSTS = 10
ARCHIVE_CACHE_ROOT = Path("data/archive/source-cache")
DAILY_CACHE_ROOT = Path("data/daily-enrichment/source-cache")
ARCHIVE_ROBOTS_KEEP_HOURS = 20
PERMANENT_ISSUES = frozenset({"http_404", "http_410", "robots_disallowed_or_unavailable",
                              "non_html_response", "redirect_to_non_article"})
OUTAGE_ISSUES = frozenset({"download_outage", "ConnectError", "ConnectTimeout", "ReadTimeout",
                           "WriteTimeout", "PoolTimeout"})
ROBOTS_ANSWERED = frozenset({200, 404, 410})


class DownloadCounters(TypedDict):
    cache_reused: int
    downloads: int
    failed: dict[str, int]
    gave_up: int
    skipped_cap: int
    skipped_time: int
    outage: bool
    outage_kept: int
    raw_dirs_deleted: int


class CaptureSummary(DownloadCounters):
    window_days: int | None
    articles_synced: int
    window_documents: int
    window_archived: int
    coverage_pct: float | None
    new_versions: dict[str, int]
    archive_bytes: int
    archive_size_warning: bool


class DayCoverage(TypedDict):
    documents: int
    archived: int
    coverage_pct: float | None


class HostCount(TypedDict):
    host: str
    documents: int


class ArchiveStatus(TypedDict):
    states: dict[str, int]
    versions: int
    archive_bytes: int
    window_days: int
    window_documents: int
    window_archived: int
    coverage_pct: float | None
    coverage_by_day: dict[str, DayCoverage]
    top_hosts_without_text: list[HostCount]


class ImportResult(TypedDict):
    source_articles: int
    selected: int
    selected_with_text: int
    documents: NotRequired[int]
    new_versions: NotRequired[int]


class CachedPage(TypedDict):
    text: str
    final_url: str | None
    http_status: int | None


def _archive_client() -> httpx.AsyncClient:
    client: httpx.AsyncClient = make_http_client(ARCHIVE_DOWNLOAD_CONCURRENCY)
    return client


@dataclass(frozen=True)
class PageFetch:
    """Where and how pages are downloaded: caches, HTTP client, per-host pause, clock."""

    cache_root: Path = ARCHIVE_CACHE_ROOT
    daily_cache_root: Path = DAILY_CACHE_ROOT
    client_factory: Callable[[], httpx.AsyncClient] = _archive_client
    host_interval: float = 1.0
    clock: Callable[[], float] = time.monotonic


@dataclass(frozen=True)
class CaptureOptions:
    """What one capture run does: the window or every article, downloads or not, a time cap."""

    scope_all: bool = False
    no_download: bool = False
    max_seconds: int | None = None


DEFAULT_CAPTURE = CaptureOptions()


@dataclass(frozen=True)
class _DueQuery:
    since: datetime | None
    now: datetime
    only: Collection[int] | None = None


def url_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def archive_articles(session: Session, articles: Iterable[Article],
                     source_keys: Mapping[int, str] | None = None) -> tuple[int, int]:
    """Upsert one document per article and add its content as a version when long enough.

    Sync, no network, no commit (the caller owns the transaction). `source_keys` maps source ids
    when the articles come from another database. Returns (documents, new versions)."""
    rows = list(articles)
    source_ids = {row.source_id for row in rows if row.source_id is not None}
    if source_keys is None:
        source_keys = dict(session.execute(  # type: ignore[arg-type]
            select(Source.id, Source.source_key).where(Source.id.in_(source_ids))).all()
        ) if source_ids else {}
    repo = ArchiveRepo(session)
    added = 0
    for row in rows:
        document = repo.upsert_document(DocumentMeta(
            url_canonical_hash=row.url_canonical_hash, url=row.url,
            url_canonical=row.url_canonical,
            source_key=source_keys.get(row.source_id) if row.source_id is not None else None,
            host=url_host(row.url_canonical or row.url), title=row.title,
            published_at=row.published_at, publication_day=row.publication_day,
            publication_status=row.publication_status, article_id=row.id,
            first_seen_at=row.discovered_at))
        content = row.content or ""
        if len(content.strip()) >= ARCHIVE_MIN_TEXT_CHARS and repo.add_version(
                document, TextVersion(content, ORIGIN_ARTICLE_CONTENT, ARTICLE_CONTENT_VERSION)):
            added += 1
    return len(rows), added


def prune_articles(session: Session, *, older_than_days: int) -> tuple[int, int]:
    """Archive, then delete, the articles past the cutoff; no commit (the caller owns it).

    Returns (deleted articles, deleted aliases)."""
    deleted: tuple[int, int] = ArticleRepo(session).prune_older_than(
        older_than_days=older_than_days, archive=lambda rows: archive_articles(session, rows))
    return deleted


def _coverage(states: list[tuple[datetime, str]]) -> tuple[int, int, float | None]:
    archived = sum(1 for _, state in states if state == STATE_ARCHIVED)
    pct = round(100.0 * archived / len(states), 1) if states else None
    return len(states), archived, pct


def _sync_window(session: Session, since: datetime | None) -> int:
    """Archive the articles first seen since `since` (all with None), in committed batches."""
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
    return synced


def _summary(session: Session, since: datetime | None, started: datetime, synced: int,
             downloads: DownloadCounters) -> CaptureSummary:
    """Window coverage and archive size after the run; `since` None is the whole archive."""
    repo = ArchiveRepo(session)
    documents, archived, pct = _coverage(repo.window_states(since))
    size = repo.size_bytes()
    return {
        "window_days": None if since is None else ARCHIVE_LOOKBACK_DAYS,
        "articles_synced": synced, "window_documents": documents, "window_archived": archived,
        "coverage_pct": pct, "new_versions": repo.new_versions_since(started), **downloads,
        "archive_bytes": size, "archive_size_warning": size >= ARCHIVE_SIZE_WARN_BYTES,
    }


def capture(session: Session, options: CaptureOptions = DEFAULT_CAPTURE, *,
            logger: logging.Logger | None = None, now: datetime | None = None,
            fetch: PageFetch | None = None) -> CaptureSummary:
    """Sync the window (or every article with `scope_all`), then, unless `no_download`, reuse or
    download pages of due documents without text; summarize."""
    fetch = fetch or PageFetch()
    max_seconds = options.max_seconds
    deadline = fetch.clock() + max_seconds if max_seconds is not None else float("inf")
    started = now or datetime.now(UTC)
    since = None if options.scope_all else started - timedelta(days=ARCHIVE_LOOKBACK_DAYS)
    synced = _sync_window(session, since)
    downloads: DownloadCounters = {
        "cache_reused": 0, "downloads": 0, "failed": {}, "gave_up": 0, "skipped_cap": 0,
        "skipped_time": 0, "outage": False, "outage_kept": 0, "raw_dirs_deleted": 0}
    if not options.no_download:
        downloads = _download_step(session, _DueQuery(since, started), deadline=deadline,
                                   fetch=fetch)
    summary = _summary(session, since, started, synced, downloads)
    if logger is not None:
        log_event(logger, event="archive_capture_finished", **summary)
    return summary


def _page_dir(root: Path, url: str) -> Path:
    return Path(root, "pages", url_key(url))


def _read_json(path: Path) -> dict[str, object] | None:
    """A page-cache file as found; readers check each value they use."""
    data: dict[str, object] | None = json.loads(path.read_text()) if path.is_file() else None
    return data


def _issues(attempt: dict[str, object]) -> list[str]:
    issues = attempt.get("issues")
    return [issue for issue in issues if isinstance(issue, str)] if isinstance(issues, list) else []


def _extracted_page(directory: Path) -> CachedPage | None:
    """Text of a completed, extracted cache attempt whose text matches its evidence hash."""
    attempt = _read_json(directory / "attempt.json")
    evidence = _read_json(directory / "evidence.json")
    text_path = directory / "text.txt"
    if (not attempt or attempt.get("state") != "completed" or not evidence
            or evidence.get("quality") != "extracted" or not text_path.is_file()):
        return None
    text = text_path.read_text(encoding="utf-8")
    if (len(text.strip()) < ARCHIVE_MIN_TEXT_CHARS
            or hashlib.sha256(text.encode()).hexdigest() != evidence.get("text_sha256")):
        return None
    response = _read_json(directory / "response.json") or {}
    final_url, http_status = response.get("final_url"), response.get("status_code")
    return {"text": text, "final_url": final_url if isinstance(final_url, str) else None,
            "http_status": http_status if isinstance(http_status, int) else None}


def _attempt_issue(attempt: dict[str, object], cache_root: Path, url: str) -> tuple[str, bool]:
    """(issue, permanent) of a failed attempt; an unanswered robots.txt is retryable."""
    # HTTP status first: it names the cause; quality issues of an error page only follow from it.
    issues = sorted(_issues(attempt), key=lambda i: (not i.startswith("http_"), i)) \
        or [f"state_{attempt.get('state')}"]
    permanent = [issue for issue in issues if issue in PERMANENT_ISSUES]
    if permanent == ["robots_disallowed_or_unavailable"]:
        parts = urlsplit(url)
        robots = _read_json(cache_root / "robots" / f"{url_key(f'{parts.scheme}://{parts.netloc}')}.json")
        if robots is not None and robots.get("status_code") not in ROBOTS_ANSWERED:
            return "robots_unavailable", False
    if permanent:
        return permanent[0], True
    return issues[0], False


def _interleave_hosts(documents: list[ArchiveDocument]) -> list[ArchiveDocument]:
    by_host: dict[str, list[ArchiveDocument]] = {}
    for document in documents:
        by_host.setdefault(document.host, []).append(document)
    queues = list(by_host.values())
    ordered: list[ArchiveDocument] = []
    while queues:
        ordered.extend(queue.pop(0) for queue in queues)
        queues = [queue for queue in queues if queue]
    return ordered


async def _dispatch(downloader: SourcePageDownloader, urls: list[str], deadline: float,
                    clock: Callable[[], float]) -> list[str]:
    """Download with a fixed worker pool; no new download starts after `deadline`."""
    queue = list(urls)
    started: list[str] = []

    async def worker() -> None:
        while queue and clock() < deadline:
            url = queue.pop(0)
            started.append(url)
            await downloader.fetch_one(url)

    await asyncio.gather(*(worker() for _ in range(ARCHIVE_DOWNLOAD_CONCURRENCY)))
    return started


def _add_page_version(repo: ArchiveRepo, document: ArchiveDocument, page: CachedPage) -> None:
    repo.add_version(document, TextVersion(page["text"], ORIGIN_SOURCE_PAGE, EXTRACTION_VERSION,
                                           final_url=page["final_url"],
                                           http_status=page["http_status"]))


class _DueSplit(NamedTuple):
    reused: int
    resumed: list[ArchiveDocument]
    targets: list[ArchiveDocument]


def _sort_due(repo: ArchiveRepo, documents: list[ArchiveDocument], *, cache_root: Path,
              daily_cache_root: Path) -> _DueSplit:
    """Reuse extracted daily-publish pages; split the rest into resumed and download targets."""
    reused = 0
    resumed: list[ArchiveDocument] = []
    targets: list[ArchiveDocument] = []
    for document in _interleave_hosts(documents):
        page = _extracted_page(_page_dir(daily_cache_root, document.url))
        if page is not None:
            _add_page_version(repo, document, page)
            document.next_attempt_at = None
            repo.session.commit()
            reused += 1
            continue
        directory = _page_dir(cache_root, document.url)
        attempt = _read_json(directory / "attempt.json")
        if attempt is not None:
            if document.state == STATE_PENDING and attempt.get("state") != "started":
                resumed.append(document)  # downloaded by a killed run, never recorded
                continue
            shutil.rmtree(directory, ignore_errors=True)
        targets.append(document)
    return _DueSplit(reused, resumed, targets)


def _cap_downloads(targets: list[ArchiveDocument]) -> tuple[list[ArchiveDocument], int]:
    """Keep targets within the per-run and per-host caps; returns (dispatch, skipped)."""
    per_host: Counter[str] = Counter()
    dispatch: list[ArchiveDocument] = []
    for document in targets:
        if (len(dispatch) >= ARCHIVE_MAX_DOWNLOADS
                or per_host[document.host] >= ARCHIVE_MAX_PER_HOST):
            continue
        per_host[document.host] += 1
        dispatch.append(document)
    return dispatch, len(targets) - len(dispatch)


def _run_downloads(dispatch: list[ArchiveDocument], *, cache: PageCache, deadline: float,
                   fetch: PageFetch) -> tuple[bool, set[str]]:
    """Download the dispatched pages; returns (outage, urls started before the deadline)."""
    if not dispatch:
        return False, set()

    async def run() -> tuple[bool, list[str]]:
        async with fetch.client_factory() as client:
            downloader = SourcePageDownloader(cache, client, DownloadLimits(
                concurrency=ARCHIVE_DOWNLOAD_CONCURRENCY, host_interval=fetch.host_interval))
            urls = list(dict.fromkeys(document.url for document in dispatch))
            return_started = await _dispatch(downloader, urls, deadline, fetch.clock)
            return downloader.outage, return_started
    outage, started_urls = asyncio.run(run())
    return outage, set(started_urls)


def _nothing_to_record(attempt: dict[str, object], outage: bool) -> bool:
    """Unfinished attempt, or only outage issues during an outage: retry as if not started."""
    if attempt.get("state") == "started":
        return True
    issues = set(_issues(attempt))
    return outage and bool(issues) and issues <= OUTAGE_ISSUES


def _record_failure(repo: ArchiveRepo, document: ArchiveDocument, attempt: dict[str, object], *,
                    cache_root: Path, now: datetime) -> tuple[str, bool]:
    """Record a failed attempt with its retry time; returns (issue, gave_up)."""
    issue, permanent = _attempt_issue(attempt, cache_root, document.url)
    attempts = (document.attempts or 0) + 1
    gave_up = permanent or attempts > len(ARCHIVE_RETRY_DELAYS)
    repo.record_attempt(document, issue=issue, gave_up=gave_up, next_attempt_at=None
                        if gave_up else now + ARCHIVE_RETRY_DELAYS[attempts - 1])
    return issue, gave_up


def _record_downloads(repo: ArchiveRepo, documents: list[ArchiveDocument], *, cache_root: Path,
                      now: datetime, outage: bool) -> tuple[int, int, Counter[str]]:
    """Record each downloaded page; returns (outage_kept, gave_up, failed issues)."""
    outage_kept = gave_up_count = 0
    failed: Counter[str] = Counter()
    for document in documents:
        directory = _page_dir(cache_root, document.url)
        attempt = _read_json(directory / "attempt.json")
        if attempt is None or _nothing_to_record(attempt, outage):
            shutil.rmtree(directory, ignore_errors=True)
            outage_kept += 1
            continue
        page = _extracted_page(directory)
        if page is not None:
            _add_page_version(repo, document, page)
            repo.record_attempt(document, issue=None, gave_up=False, next_attempt_at=None)
        else:
            issue, gave_up = _record_failure(repo, document, attempt, cache_root=cache_root,
                                             now=now)
            failed[issue] += 1
            gave_up_count += int(gave_up)
        repo.session.commit()
    return outage_kept, gave_up_count, failed


def _download_step(session: Session, due: _DueQuery, *, deadline: float,
                   fetch: PageFetch) -> DownloadCounters:
    repo = ArchiveRepo(session)
    cache = PageCache(fetch.cache_root)  # before any write: it creates the cache dirs
    split = _sort_due(repo, repo.due(due.since, due.now, ids=due.only),
                      cache_root=fetch.cache_root, daily_cache_root=fetch.daily_cache_root)
    dispatch, skipped_cap = _cap_downloads(split.targets)
    outage, started = _run_downloads(dispatch, cache=cache, deadline=deadline, fetch=fetch)
    outage_kept, gave_up, failed = _record_downloads(
        repo, split.resumed + [d for d in dispatch if d.url in started],
        cache_root=fetch.cache_root, now=due.now, outage=outage)
    return {"cache_reused": split.reused, "downloads": len(started), "gave_up": gave_up,
            "skipped_cap": skipped_cap,
            "skipped_time": sum(1 for document in dispatch if document.url not in started),
            "outage": outage, "outage_kept": outage_kept, "failed": dict(failed),
            "raw_dirs_deleted": _clean_cache(fetch.cache_root)}


def download_documents(session: Session, document_ids: Collection[int], *,
                       now: datetime | None = None,
                       fetch: PageFetch | None = None) -> DownloadCounters:
    """Reuse or download the pages of the given due documents only, with every rule of the
    capture; returns its download counters (`downloads`, `failed`, `outage`, ...)."""
    return _download_step(session, _DueQuery(None, now or datetime.now(UTC), document_ids),
                          deadline=float("inf"), fetch=fetch or PageFetch())


def dedupe_page_cache(roots: Iterable[Path], *, apply: bool = False) -> dict[str, int]:
    """Remove the duplicate page.html that older cache dirs hold next to body.bin.

    A dir qualifies only when body.bin and response.json exist, so the page can be rebuilt.
    Dry run unless apply is set.
    """
    result = {"dirs": 0, "files": 0, "bytes": 0}
    for root in roots:
        pages = root / "pages"
        for directory in pages.iterdir() if pages.is_dir() else ():
            duplicate = directory / "page.html"
            if not (duplicate.is_file() and (directory / "body.bin").is_file()
                    and (directory / "response.json").is_file()):
                continue
            result["dirs"] += 1
            result["files"] += 1
            result["bytes"] += duplicate.stat().st_size
            if apply:
                duplicate.unlink()
    return result


def _clean_cache(cache_root: Path) -> int:
    """Delete page dirs older than ARCHIVE_RAW_KEEP_DAYS and stale robots files."""
    now = time.time()
    deleted = 0
    pages = cache_root / "pages"
    for directory in pages.iterdir() if pages.is_dir() else ():
        if not directory.is_dir():
            continue
        newest = max((path.stat().st_mtime for path in directory.iterdir()),
                     default=directory.stat().st_mtime)
        if newest < now - ARCHIVE_RAW_KEEP_DAYS * 86400:
            shutil.rmtree(directory, ignore_errors=True)
            deleted += 1
    robots = cache_root / "robots"
    for path in robots.glob("*.json") if robots.is_dir() else ():
        if path.stat().st_mtime < now - ARCHIVE_ROBOTS_KEEP_HOURS * 3600:
            path.unlink(missing_ok=True)
    return deleted


def _day_coverage(rows: list[tuple[datetime, str]]) -> DayCoverage:
    documents, archived, pct = _coverage(rows)
    return {"documents": documents, "archived": archived, "coverage_pct": pct}


def status(session: Session, *, now: datetime | None = None) -> ArchiveStatus:
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
        "coverage_by_day": {day: _day_coverage(rows) for day, rows in sorted(by_day.items())},
        "top_hosts_without_text": [{"host": host, "documents": count}
                                   for host, count in repo.hosts_without_text(STATUS_TOP_HOSTS)],
    }


IMPORT_COLUMNS = (Article.id, Article.source_id, Article.title, Article.url, Article.url_canonical,
                  Article.url_canonical_hash, Article.content, Article.published_at,
                  Article.publication_day, Article.publication_status, Article.discovered_at)


def _import_batches(session: Session, source: Connection, selected: list[str],
                    source_keys: dict[int, str], apply: bool) -> tuple[int, int, int]:
    """(selected with text, documents, versions) over committed batches of `selected`;
    archives only with `apply`."""
    with_text = documents = versions = 0
    for start in range(0, len(selected), CAPTURE_BATCH_SIZE):
        chunk = selected[start:start + CAPTURE_BATCH_SIZE]
        rows = [Article(**row._asdict()) for row in source.execute(
            select(*IMPORT_COLUMNS).where(Article.url_canonical_hash.in_(chunk))).all()]
        with_text += sum(len((row.content or "").strip()) >= ARCHIVE_MIN_TEXT_CHARS
                         for row in rows)
        if apply:
            batch_documents, batch_versions = archive_articles(session, rows, source_keys)
            documents += batch_documents
            versions += batch_versions
            session.commit()
    return with_text, documents, versions


def import_db(session: Session, source_url: str, *, apply: bool = False) -> ImportResult:
    """Archive articles of another database (a restored dump) whose hash is neither a current
    article nor an archive document. The source is only read; dry run unless `apply`."""
    url = make_url(source_url)
    if url.get_backend_name() == "sqlite" and not Path(url.database or "").is_file():
        raise ValueError(f"source database file not found: {url.database}")
    current = set(session.scalars(select(Article.url_canonical_hash)))
    current |= set(session.scalars(select(ArchiveDocument.url_canonical_hash)))
    engine = create_engine(source_url, future=True)
    try:
        with engine.connect() as source:
            if not inspect(source).has_table("articles"):
                raise ValueError("source database has no articles table")
            hashes = list(source.scalars(select(Article.url_canonical_hash)))
            selected = sorted(set(hashes) - current)
            source_keys = {int(i): str(k) for i, k in source.execute(
                select(Source.id, Source.source_key)).all()}
            with_text, documents, versions = _import_batches(session, source, selected,
                                                             source_keys, apply)
            source.rollback()
    finally:
        engine.dispose()
    result: ImportResult = {"source_articles": len(hashes), "selected": len(selected),
                            "selected_with_text": with_text}
    if apply:
        result.update({"documents": documents, "new_versions": versions})
    return result


def count_old_articles(session_factory: Callable[[], Session], older_than_days: int) -> int:
    """Articles past the cutoff (the prune dry run)."""
    with session_factory() as session:
        count: int = ArticleRepo(session).count_older_than(older_than_days=older_than_days)
        return count


def prune_old_articles(session_factory: Callable[[], Session], older_than_days: int
                       ) -> tuple[int, int]:
    """`prune_articles` in its own session, committed."""
    with session_factory() as session:
        deleted = prune_articles(session, older_than_days=older_than_days)
        session.commit()
        return deleted


def purge_archive(session_factory: Callable[[], Session], *, url: str | None,
                  source_key: str | None, host: str | None, apply: bool) -> tuple[int, int]:
    """Documents and versions of one URL, source or host; deleted and committed with `apply`."""
    with session_factory() as session:
        counts: tuple[int, int] = ArchiveRepo(session).purge(
            url=url, source_key=source_key, host=host, apply=apply)
        session.commit()
        return counts
