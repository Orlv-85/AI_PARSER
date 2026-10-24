"""HTML path: fetch and persist the articles behind a list page."""
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
from app.core.ingestion.pipeline.weekly_hooks import _record_weekly_observation
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


# pylint: disable=too-many-branches,too-many-statements
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
    new_count = 0
    duplicate_count = 0
    skipped_known_items = 0
    early_stop_hit = False
    fetched_articles = 0
    html_known_streak = 0
    html_known_streak_stop = settings.html_known_streak_stop
    html_max_links_per_source = settings.html_max_links_per_source
    batch_mode = settings.article_batch_upsert_enabled
    admission_enabled = admission_state is not None and admission_state.enabled
    links = [link for link in links if url_exclusion_reason(str(link)) is None]
    capped_links = links
    if html_max_links_per_source is not None and html_max_links_per_source >= 0:
        capped_links = links[:html_max_links_per_source]
        if len(capped_links) < len(links) and quality_flags is not None:
            quality_flags.append("truncated")
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
    queued_rows: list[dict[str, object]] = []
    fetcher = Fetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        per_source_min_interval_seconds=settings.per_source_min_interval_seconds,
        http_max_connections=settings.fetch_http_max_connections,
        http_max_keepalive_connections=settings.fetch_http_max_keepalive_connections,
    )

    try:
        if admission_enabled:
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

        for link, canonical, canonical_hash in canonical_by_link:
            ph_key = placeholder_keys.get(canonical_hash, "")
            if canonical_hash in known_hashes:
                duplicate_count += 1
                skipped_known_items += 1
                if admission_enabled:
                    settle_pending(article_repo.session, key=ph_key)
                html_known_streak += 1
                if 0 < html_known_streak_stop <= html_known_streak:
                    early_stop_hit = True
                    break
                continue

            html_known_streak = 0
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
                continue
            if item is None:
                if exclusions:
                    settle_pending(article_repo.session, key=ph_key)
                    continue
                if quality_flags is not None:
                    quality_flags.append("parser_failure")
                continue
            reason = _item_exclusion_reason(item)
            if reason:
                log_exclusion(str(item.url), reason)
                if admission_enabled:
                    settle_pending(article_repo.session, key=ph_key)
                continue
            fetched_articles += 1
            _record_weekly_observation(article_repo, db_source_id, item)
            if (item.published_at is None and item.publication_evidence_at is None
                    and quality_flags is not None):
                quality_flags.append("unknown_publication_date")

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
            if batch_mode:
                queued_rows.append(row)
            else:
                _, is_new = article_repo.insert_article(**row)
                if is_new:
                    new_count += 1
                else:
                    duplicate_count += 1
            known_hashes.add(canonical_hash)
        if batch_mode:
            batch_new, batch_duplicates = _upsert_article_rows(
                article_repo=article_repo,
                rows=queued_rows,
            )
            new_count += batch_new
            duplicate_count += batch_duplicates
    finally:
        fetcher.close()
    return fetched_articles, new_count, duplicate_count, skipped_known_items, early_stop_hit
