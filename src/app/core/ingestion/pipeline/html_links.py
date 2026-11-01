"""HTML path: fetch and persist the articles behind a list page."""
from dataclasses import dataclass, field
from typing import Any

from app.config.settings import Settings
from app.config.sources import SourceConfig
from app.core.canonicalize import canonical_url_hash, canonicalize_url
from app.core.ingestion.pipeline.models import AdmissionState
from app.core.ingestion.pipeline.rows import (
    _build_article_row,
    _item_exclusion_reason,
    _upsert_article_rows,
)
from app.core.ingestion.pipeline.screening import _html_placeholder_key, _screen_candidate
from app.core.jev import JevRelevanceScorer
from app.ingest.fetcher import Fetcher
from app.ingest.html import (
    fetch_html_article,
)
from app.ingest.page_filter import (
    log_exclusion,
    url_exclusion_reason,
)
from app.storage.admission import (
    settle_pending,
    upsert_pending,
)
from app.storage.article_repo import ArticleRepo


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


def _upsert_placeholders(
    *,
    canonical_by_link: list[tuple[str, str, str]],
    known_hashes: set[str],
    placeholder_keys: dict[str, str],
    db_source_id: int,
    article_repo: ArticleRepo,
    settings: Settings,
) -> None:
    for link, _canonical, canonical_hash in canonical_by_link:
        if canonical_hash in known_hashes:
            settle_pending(article_repo.session, key=placeholder_keys[canonical_hash])
            continue
        upsert_pending(
            article_repo.session,
            key=placeholder_keys[canonical_hash],
            url_canonical_hash=canonical_hash,
            source_id=db_source_id,
            payload={"kind": "html_link", "url": link},
            evidence_hash="",
            policy_version=settings.semantic_admission_policy_version,
            model=settings.jev_model,
        )


def _count_known_link(
    tally: _HtmlTally, *, ph_key: str, admission_enabled: bool, article_repo: ArticleRepo,
    streak_stop: int,
) -> bool:
    """Count a stored link; True when the known streak says to stop."""
    tally.duplicate_count += 1
    tally.skipped_known_items += 1
    if admission_enabled:
        settle_pending(article_repo.session, key=ph_key)
    tally.known_streak += 1
    if 0 < streak_stop <= tally.known_streak:
        tally.early_stop_hit = True
        return True
    return False


def _fetch_new_item(
    tally: _HtmlTally,
    *,
    link: str,
    ph_key: str,
    config: SourceConfig,
    article_repo: ArticleRepo,
    settings: Settings,
    fetcher: Fetcher,
    quality_flags: list[str] | None,
    admission_enabled: bool,
) -> Any | None:
    """Fetch one article page; None when it failed or was excluded (already settled/flagged)."""
    exclusions: list[str] = []
    fetch_options: dict[str, Any] = {}
    if admission_enabled:
        fetch_options["on_exclusion"] = exclusions.append
    try:
        item = fetch_html_article(
            source=config,
            url=str(link),
            timeout_seconds=settings.request_timeout_seconds,
            fetcher=fetcher,
            **fetch_options,
        )
    except Exception:
        if quality_flags is not None:
            quality_flags.append("article_failure")
        return None
    if item is None:
        if exclusions:
            settle_pending(article_repo.session, key=ph_key)
            return None
        if quality_flags is not None:
            quality_flags.append("parser_failure")
        return None
    reason = _item_exclusion_reason(item)
    if reason:
        log_exclusion(str(item.url), reason)
        if admission_enabled:
            settle_pending(article_repo.session, key=ph_key)
        return None
    tally.fetched_articles += 1
    if (item.published_at is None and item.publication_evidence_at is None
            and quality_flags is not None):
        quality_flags.append("unknown_publication_date")
    return item


def _store_row(
    tally: _HtmlTally, row: dict[str, object], *, batch_mode: bool, article_repo: ArticleRepo,
) -> None:
    if batch_mode:
        tally.queued_rows.append(row)
        return
    _, is_new = article_repo.insert_article(**row)
    if is_new:
        tally.new_count += 1
    else:
        tally.duplicate_count += 1


def _process_html_links_two_stage(
    *,
    links: list[str],
    config: SourceConfig,
    db_source_id: int,
    article_repo: ArticleRepo,
    settings: Settings,
    relevance_scorer: JevRelevanceScorer | None = None,
    quality_flags: list[str] | None = None,
    admission_state: AdmissionState | None = None,
) -> tuple[int, int, int, int, bool]:
    tally = _HtmlTally()
    batch_mode = settings.article_batch_upsert_enabled
    admission_enabled = admission_state is not None and admission_state.enabled
    capped_links = _capped_links(links, settings, quality_flags)
    canonical_by_link: list[tuple[str, str, str]] = [
        (str(link), canonicalize_url(str(link)), canonical_url_hash(str(link)))
        for link in capped_links
    ]
    # Stored hashes; the article loop adds each hash it stores, so in-run repeats count as known.
    known_hashes = article_repo.existing_canonical_hashes([h for _, _, h in canonical_by_link])
    placeholder_keys = {
        canonical_hash: _html_placeholder_key(settings, canonical_hash)
        for _, _, canonical_hash in canonical_by_link
    } if admission_enabled else {}
    fetcher = Fetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        per_source_min_interval_seconds=settings.per_source_min_interval_seconds,
        http_max_connections=settings.fetch_http_max_connections,
        http_max_keepalive_connections=settings.fetch_http_max_keepalive_connections,
    )

    try:
        if admission_enabled:
            _upsert_placeholders(
                canonical_by_link=canonical_by_link,
                known_hashes=known_hashes,
                placeholder_keys=placeholder_keys,
                db_source_id=db_source_id,
                article_repo=article_repo,
                settings=settings,
            )

        for link, canonical, canonical_hash in canonical_by_link:
            ph_key = placeholder_keys.get(canonical_hash, "")
            if canonical_hash in known_hashes:
                if _count_known_link(
                    tally, ph_key=ph_key, admission_enabled=admission_enabled,
                    article_repo=article_repo, streak_stop=settings.html_known_streak_stop,
                ):
                    break
                continue

            tally.known_streak = 0
            item = _fetch_new_item(
                tally, link=link, ph_key=ph_key, config=config, article_repo=article_repo,
                settings=settings, fetcher=fetcher, quality_flags=quality_flags,
                admission_enabled=admission_enabled,
            )
            if item is None:
                continue

            assessment = None
            if admission_enabled:
                action, assessment = _screen_candidate(
                    item=item,
                    config=config,
                    db_source_id=db_source_id,
                    article_repo=article_repo,
                    settings=settings,
                    relevance_scorer=relevance_scorer,
                    admission_state=admission_state,
                    canonical_hash=canonical_hash,
                    canonical_url=canonical,
                )
                # Screened: the body (or its decision) now holds the candidate, not the link.
                settle_pending(article_repo.session, key=ph_key)
                if action == "paused":
                    break
                if action != "accept":
                    continue
            else:
                assessment = (
                    relevance_scorer.classify(item) if relevance_scorer is not None else None
                )

            row = _build_article_row(
                item=item,
                config=config,
                db_source_id=db_source_id,
                canonical=canonical,
                canonical_hash=canonical_hash,
                assessment=assessment,
                admission_enabled=admission_enabled,
            )
            if row is None:
                continue
            _store_row(tally, row, batch_mode=batch_mode, article_repo=article_repo)
            known_hashes.add(canonical_hash)
        if batch_mode:
            batch_new, batch_duplicates = _upsert_article_rows(
                article_repo=article_repo,
                rows=tally.queued_rows,
            )
            tally.new_count += batch_new
            tally.duplicate_count += batch_duplicates
    finally:
        fetcher.close()
    return (
        tally.fetched_articles, tally.new_count, tally.duplicate_count,
        tally.skipped_known_items, tally.early_stop_hit,
    )
