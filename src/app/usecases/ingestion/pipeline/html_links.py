"""HTML path: fetch and persist the articles behind a list page."""
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from app.config.settings import Settings
from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.ingestion.page_filter import (
    log_exclusion,
    url_exclusion_reason,
)
from app.ingest.fetcher import Fetcher
from app.ingest.html import (
    fetch_html_article,
)
from app.storage.admission import (
    settle_pending,
    upsert_pending,
)
from app.usecases.ingestion.pipeline.models import SourceRun
from app.usecases.ingestion.pipeline.rows import (
    _item_exclusion_reason,
    _upsert_article_rows,
)
from app.usecases.ingestion.pipeline.screening import _assessed_row, _html_placeholder_key


@dataclass
class _HtmlTally:
    new_count: int = 0
    duplicate_count: int = 0
    skipped_known_items: int = 0
    fetched_articles: int = 0
    known_streak: int = 0
    early_stop_hit: bool = False
    queued_rows: list[dict[str, object]] = field(default_factory=list)


def _capped_links(
    links: list[str], settings: Settings, quality_flags: list[str] | None,
) -> list[str]:
    links = [link for link in links if url_exclusion_reason(str(link)) is None]
    max_links = settings.html_max_links_per_source
    if max_links is None or max_links < 0:
        return links
    capped = links[:max_links]
    if len(capped) < len(links) and quality_flags is not None:
        quality_flags.append("truncated")
    return capped


@dataclass(kw_only=True)
class _HtmlRun(SourceRun):
    quality_flags: list[str] | None
    fetcher: Fetcher

    def flag(self, name: str) -> None:
        if self.quality_flags is not None:
            self.quality_flags.append(name)


def _make_fetcher(settings: Settings) -> Fetcher:
    return Fetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        per_source_min_interval_seconds=settings.per_source_min_interval_seconds,
        http_max_connections=settings.fetch_http_max_connections,
        http_max_keepalive_connections=settings.fetch_http_max_keepalive_connections,
    )


def _upsert_placeholders(
    run: _HtmlRun,
    *,
    canonical_by_link: list[tuple[str, str, str]],
    known_hashes: set[str],
    placeholder_keys: dict[str, str],
) -> None:
    for link, _canonical, canonical_hash in canonical_by_link:
        if canonical_hash in known_hashes:
            settle_pending(run.article_repo.session, key=placeholder_keys[canonical_hash])
            continue
        upsert_pending(
            run.article_repo.session,
            key=placeholder_keys[canonical_hash],
            url_canonical_hash=canonical_hash,
            source_id=run.db_source_id,
            payload={"kind": "html_link", "url": link},
            evidence_hash="",
            policy_version=run.settings.semantic_admission_policy_version,
            model=run.settings.jev_model,
        )


def _count_known_link(run: _HtmlRun, tally: _HtmlTally, *, ph_key: str) -> bool:
    """Count a stored link; True when the known streak says to stop."""
    tally.duplicate_count += 1
    tally.skipped_known_items += 1
    if run.admission_enabled:
        settle_pending(run.article_repo.session, key=ph_key)
    tally.known_streak += 1
    if 0 < run.settings.html_known_streak_stop <= tally.known_streak:
        tally.early_stop_hit = True
        return True
    return False


def _fetch_new_item(run: _HtmlRun, tally: _HtmlTally, *, link: str, ph_key: str) -> Any | None:
    """Fetch one article page; None when it failed or was excluded (already settled/flagged)."""
    exclusions: list[str] = []
    fetch_options: dict[str, Any] = {}
    if run.admission_enabled:
        fetch_options["on_exclusion"] = exclusions.append
    try:
        item = fetch_html_article(
            source=run.config,
            url=str(link),
            timeout_seconds=run.settings.request_timeout_seconds,
            fetcher=run.fetcher,
            **fetch_options,
        )
    except Exception:
        run.flag("article_failure")
        return None
    if item is None:
        if exclusions:
            settle_pending(run.article_repo.session, key=ph_key)
            return None
        run.flag("parser_failure")
        return None
    reason = _item_exclusion_reason(item)
    if reason:
        log_exclusion(str(item.url), reason)
        if run.admission_enabled:
            settle_pending(run.article_repo.session, key=ph_key)
        return None
    tally.fetched_articles += 1
    if item.published_at is None and item.publication_evidence_at is None:
        run.flag("unknown_publication_date")
    return item


def _store_row(run: _HtmlRun, tally: _HtmlTally, row: dict[str, object]) -> None:
    if run.settings.article_batch_upsert_enabled:
        tally.queued_rows.append(row)
        return
    _, is_new = run.article_repo.insert_article(row)
    if is_new:
        tally.new_count += 1
    else:
        tally.duplicate_count += 1


class _Link(NamedTuple):
    url: str
    canonical: str
    canonical_hash: str
    ph_key: str


def _process_link(run: _HtmlRun, tally: _HtmlTally, link: _Link, known_hashes: set[str]) -> bool:
    """Persist one list-page link; True when the source loop stops (known streak or pause)."""
    canonical, canonical_hash, ph_key = link.canonical, link.canonical_hash, link.ph_key
    if canonical_hash in known_hashes:
        return _count_known_link(run, tally, ph_key=ph_key)
    tally.known_streak = 0
    item = _fetch_new_item(run, tally, link=link.url, ph_key=ph_key)
    if item is None:
        return False
    assessed: tuple[str, dict[str, object] | None] = _assessed_row(
        run, item, canonical=canonical, canonical_hash=canonical_hash,
    )
    action, row = assessed
    if run.admission_enabled:
        # Screened: the body (or its decision) now holds the candidate, not the link.
        settle_pending(run.article_repo.session, key=ph_key)
    if row is not None:
        _store_row(run, tally, row)
        known_hashes.add(canonical_hash)
    return action == "paused"


def _flush_queued_rows(run: _HtmlRun, tally: _HtmlTally) -> None:
    if not run.settings.article_batch_upsert_enabled:
        return
    batch_new, batch_duplicates = _upsert_article_rows(
        article_repo=run.article_repo,
        rows=tally.queued_rows,
    )
    tally.new_count += batch_new
    tally.duplicate_count += batch_duplicates


def _process_html_links_two_stage(
    source: SourceRun, links: list[str], quality_flags: list[str] | None = None,
) -> tuple[int, int, int, int, bool]:
    tally = _HtmlTally()
    settings, article_repo = source.settings, source.article_repo
    admission_enabled = source.admission_enabled
    canonical_by_link: list[tuple[str, str, str]] = [
        (str(link), canonicalize_url(str(link)), canonical_url_hash(str(link)))
        for link in _capped_links(links, settings, quality_flags)
    ]
    # Stored hashes; the article loop adds each hash it stores, so in-run repeats count as known.
    known_hashes = article_repo.existing_canonical_hashes([h for _, _, h in canonical_by_link])
    placeholder_keys = {
        canonical_hash: _html_placeholder_key(settings, canonical_hash)
        for _, _, canonical_hash in canonical_by_link
    } if admission_enabled else {}
    run = _HtmlRun(**vars(source), quality_flags=quality_flags, fetcher=_make_fetcher(settings))

    try:
        if admission_enabled:
            _upsert_placeholders(
                run,
                canonical_by_link=canonical_by_link,
                known_hashes=known_hashes,
                placeholder_keys=placeholder_keys,
            )
        for link, canonical, canonical_hash in canonical_by_link:
            entry = _Link(link, canonical, canonical_hash, placeholder_keys.get(canonical_hash, ""))
            if _process_link(run, tally, entry, known_hashes):
                break
        _flush_queued_rows(run, tally)
    finally:
        run.fetcher.close()
    return (
        tally.fetched_articles, tally.new_count, tally.duplicate_count,
        tally.skipped_known_items, tally.early_stop_hit,
    )
