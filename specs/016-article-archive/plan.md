# Implementation Plan: Full-text article archive (A1, A3)

**Branch**: `016-article-archive` | **Date**: 2026-10-23 | **Spec**: [spec.md](spec.md)
**Input**: `specs/016-article-archive/spec.md`; measurements in `records/report-plan-2026-10-23.md`

## Summary

Two archive tables in the application PostgreSQL, with no foreign key to `articles`, hold one
document per canonical URL hash and append-only text versions. `ai-news prune` archives what it
deletes. A nightly `ai-news archive capture` job (own systemd timer, 03:00 UTC, shared host lock)
copies new articles' stored content without network, and for articles without full text reuses
pages already downloaded by daily-publish or downloads them through the existing
`SourcePageDownloader`, with retries on a fixed schedule. Nothing in web, API or MCP reads the
archive.

## Technical Context

**Language/Version**: Python 3.14
**Primary Dependencies**: SQLAlchemy, Alembic, Typer, httpx; existing `app.storage.article_evidence_cache`
(`PageCache`, `SourcePageDownloader`, `make_http_client`, `inspect_page`, `EXTRACTION_VERSION`)
**Storage**: PostgreSQL 18.2 in production (SQLite for tests and local); file cache under `data/archive/`
**Testing**: pytest; `httpx.MockTransport` for downloads; SQLite sessions; no network
**Target Platform**: production VPS (25 GB disk, 8.7 GB free, 1.9 GB RAM), docker compose, systemd timers
**Performance Goals**: normal night (about 100 new articles, under 20 downloads) under 15 minutes
**Constraints**: never block or fail fetch, digest or signals; inside the host lock; polite downloads
**Scale/Scope**: 7079 articles today; about 92 new articles per day; about 10 KB of text each

## Where the archive lives (A1)

Decision: same PostgreSQL, two tables; no files for now.

- Off-site backups (A0) already cover the database; files would need their own backup path.
- Size is small: all article text today is 29 MB (24 MB TOAST); growth about 0.35 GB per year.
- Cold files (JSONL per month, compressed) are deferred until the archive passes
  `ARCHIVE_SIZE_WARN_BYTES` (2 GB); `archive status` and the capture log report the size.

### Data model

`archive_documents` (one row per URL identity; survives `articles`):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | int PK | |
| `url_canonical_hash` | str(64), unique | identity, same as `articles.url_canonical_hash` |
| `url`, `url_canonical` | str(2048) | from the article |
| `source_key` | str(64) | copied, no FK (sources can be renamed or removed) |
| `host` | str(255), index | lowercase host without `www.`; purge and per-host stats |
| `title` | str(512) | latest known |
| `published_at`, `publication_day`, `publication_status` | as in `articles` | latest known |
| `article_id` | int, nullable, index | last known `articles.id`, no FK (pattern of `signal_mentions`) |
| `first_seen_at` | datetime | `articles.discovered_at` of the first sync |
| `state` | str(16), index | `pending`, `archived`, `failed`, `gave_up` |
| `attempts` | int | download attempts made by the capture |
| `next_attempt_at` | datetime, nullable | due time of the next download |
| `last_issue` | str(64), nullable | last failure issue (exception class or quality issue) |
| `created_at`, `updated_at` | datetime | |

`archive_texts` (append-only versions):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | int PK | later derived tables (A4 chunks, A5 facts) key on this id |
| `document_id` | int FK `archive_documents.id`, index | inside the archive only |
| `text` | text | clean extracted text |
| `text_chars` | int | |
| `text_sha256` | str(64) | unique together with `document_id` |
| `origin` | str(32) | `article_content` or `source_page` |
| `extraction_version` | str(64) | `EXTRACTION_VERSION` for pages; `ARTICLE_CONTENT_VERSION` for stored content (ingestion does not record its extractor) |
| `final_url` | str(2048), nullable | after redirects (downloads) |
| `http_status` | int, nullable | downloads |
| `issues` | text (JSON list) | quality issues, e.g. `paywall`; empty for stored content |
| `captured_at` | datetime | |

- A version is stored only when its text has at least `ARCHIVE_MIN_TEXT_CHARS` (300, the same bar
  as `inspect_page` and daily `source_row`) and, for pages, quality `extracted`.
- Latest text of a document: its version with the highest `id`.
- A document is `archived` when it has at least one version.
- Duplicates across sources: none at storage time; identity is the canonical hash (ingestion
  records no aliases; `article_aliases` has 0 rows in production). Story grouping stays a read-time
  concern, as in ingestion.
- No `author`, `language` or license fields: nothing extracts them today; A5 adds nullable columns.
  Paywall and access flags live in `issues`.
- Migration `<rev>_add_article_archive.py`, `down_revision = "c3a8e5d27f14"` (current head);
  additive; downgrade drops both tables.

### Retention, purge, access

- `ArticleRepo.prune_older_than` calls `archive_articles(session, rows)` for the rows it is about to
  delete (sync, no network), in the same transaction, then deletes. Every caller (deploy, `scripts/db_maintenance.sh`,
  CLI) is covered. `prune --dry-run` stays read-only.
- `entities purge-evidence` and any future cleanup never touch archive tables (invariant + test).
- `ai-news archive purge (--url U | --source KEY | --host H) [--apply]`: dry run prints document and
  version counts; `--apply` deletes those documents and their versions and prints the counts.
- Access: no module under `app/web`, `app/mcp` or `app/web/routes` imports `app.storage.archive` or
  `app.core.archive`; a test enforces it. Text is never exposed, also not on admin pages.

### Raw HTML

Not stored in the database. The capture's own file cache (`data/archive/source-cache/`, a `PageCache`
root, 0700) keeps `body.bin` and `page.html` for `ARCHIVE_RAW_KEEP_DAYS` (14) to allow
re-extraction after an extractor fix; the capture deletes older page directories at the end of each
run. Budget: under 20 pages a day x about 0.86 MB per page directory (measured) x 14 days, about 0.25 GB.

## Daily capture (A3)

### Where in the nightly flow

Own job `scripts/run_daily_archive_job.sh`, systemd timer `ai-news-daily-archive` at 03:00 UTC,
installed by `scripts/install_daily_timers.sh` (run by every deploy).

- Fetch runs 01:00 UTC (about 28 minutes on 2026-10-23), digest 02:00 UTC (about 10 minutes, plus
  signals). At 03:00 both are normally done; if not, the job waits on the shared lock
  `/tmp/ai-news-auto-update.lock` (`flock -w 1800`).
- After the digest, so pages daily-publish downloaded for articles without text are reused instead
  of downloaded twice.
- Own timer, not a step in the fetch or digest script: a capture failure, hang or kill cannot change
  their exit status or budget. The 4-hour budget of fetch and digest is untouched.
- Limits: `TimeoutStartSec=3600`; inside, `timeout -k 30 1680 docker compose run --rm --name
  ai-news-archive app ai-news archive capture --max-seconds 1500`; a lock timeout or a failed
  capture logs one line and exits 0 (the log and `archive status` show it; nightly health does not
  check the archive in this spec).

### Capture steps (`app/core/archive/capture.py`)

```text
capture(session, settings, *, scope_all=False, no_download=False, max_seconds)
  1 window   = articles with discovered_at >= now - ARCHIVE_LOOKBACK_DAYS (all with --all)
  2 sync     = archive_articles(window): upsert document metadata; add article_content version
               when content >= ARCHIVE_MIN_TEXT_CHARS; commit per batch of 200
  3 due      = documents of the window, state pending/failed, no version,
               next_attempt_at null or <= now, ordered by first_seen_at desc
  4 reuse    = daily-publish cache (data/daily-enrichment/source-cache): attempt completed,
               quality extracted, text sha matches evidence -> source_page version, no request
  5 download = rest, capped by ARCHIVE_MAX_DOWNLOADS and ARCHIVE_MAX_PER_HOST, stop dispatch at
               max_seconds; SourcePageDownloader(PageCache(data/archive/source-cache),
               make_http_client(ARCHIVE_DOWNLOAD_CONCURRENCY), concurrency=ARCHIVE_DOWNLOAD_CONCURRENCY)
  6 record   = per document: version or failure (retry schedule); commit per document
  7 clean    = delete archive cache page dirs older than ARCHIVE_RAW_KEEP_DAYS
  8 log      = archive_capture_finished JSON line; CLI prints the same JSON
```

- `--no-download` stops after step 2 (the seed: `archive capture --all --no-download`).
- Documents outside the window without text stay `pending`; A2 decides about them.

### Politeness (reused, not new)

`SourcePageDownloader` already: robots.txt per origin (cached in the cache root, disallow on
unknown answers), `Crawl-delay`, per-host interval 1 s, manual redirects (at most 5) with the
non-article check, 20 s timeout (10 s connect), 10 MB body cap, 429 pauses the host for the run,
503 three times pauses it, 10 hosts with connection errors stop the run (`outage`). User agent:
`DEFAULT_USER_AGENT` of the fetcher, the same identity that fetched the feeds. New in the capture:
`ARCHIVE_MAX_DOWNLOADS` (200) per run, `ARCHIVE_MAX_PER_HOST` (20) per run, concurrency 4.

### Retry and give up

`PageCache` allows one attempt per URL per cache root. For a retry the capture deletes that URL's
page directory in the archive cache (never in the daily-publish cache) before downloading again.

| Result | State | Next |
| --- | --- | --- |
| extracted, text >= min | `archived` | none |
| `http_404`, `http_410`, `robots_disallowed_or_unavailable`, `non_html_response`, `redirect_to_non_article` | `gave_up` | none |
| anything else (`http_403`, `http_5xx`, timeouts, `host_rate_limit_or_unavailable`, `blocked_or_error_page`, `paywall`, `short_or_empty_extraction`, ...) | `failed` | `now + ARCHIVE_RETRY_DELAYS[attempts-1]` (1, 3, 7 days); after the last: `gave_up` |
| `download_outage` (run-level) | unchanged | not counted as an attempt |
| skipped by cap or time | unchanged | next run |

So a page gets at most 4 downloads over about 11 days. openai.com (403 to the server) will reach
`gave_up` per article; a separate investigation exists (`docs/prompt-openai-source-investigation-2026-10-23.md`).

### Coverage metrics

`archive_capture_finished` fields: `window_days`, `window_documents`, `window_archived`,
`coverage_pct`, `new_versions` (by origin), `cache_reused`, `downloads`, `failed` (by issue),
`gave_up`, `skipped_cap`, `skipped_time`, `raw_dirs_deleted`, `archive_bytes`,
`archive_size_warning`. `archive status` prints totals by state, coverage per first-seen day of
the window, top hosts without text, table sizes.

### Constants (`app/core/archive/capture.py`)

| Name | Value | Why |
| --- | --- | --- |
| `ARCHIVE_MIN_TEXT_CHARS` | 300 | same bar as `inspect_page` and daily `source_row` |
| `ARCHIVE_LOOKBACK_DAYS` | 7 | covers retries of the first delays; older gaps are A2 |
| `ARCHIVE_RETRY_DELAYS` | 1, 3, 7 days | transient errors and late publication; pages that fail for 11 days rarely recover |
| `ARCHIVE_MAX_DOWNLOADS` | 200 | about 10x a normal night (93 short of 1185 in 11 days) |
| `ARCHIVE_MAX_PER_HOST` | 20 | one host cannot use the run; equals the RSS full-text item cap |
| `ARCHIVE_DOWNLOAD_CONCURRENCY` | 4 | same as daily-publish `acquire` |
| `ARCHIVE_RAW_KEEP_DAYS` | 14 | re-extraction window; bounded disk |
| `ARCHIVE_SIZE_WARN_BYTES` | 2 GB | about 5 years at current growth; time to decide cold files |
| `ARTICLE_CONTENT_VERSION` | `article-content-1` | marks text copied from `articles.content` |

## Code doc (implementer creates in the first code PR)

`src/app/core/archive/capture.md`, named by the docstring of `capture.py`:

```text
<!-- code-doc
module: src/app/core/archive/capture.py
covers:
  - src/app/core/archive/*.py
  - src/app/storage/archive.py
  - src/app/storage/migrations/versions/*article_archive*.py
  - scripts/run_daily_archive_job.sh
-->
```

Sections per AGENTS.md: Behavior (Mermaid of sync -> reuse -> download -> record -> clean -> log),
Decisions, Invariants, Code map, Tests. Register it in `docs/README.md`, `README.md`,
`src/app/README.md`. The prune rule is also added to the doc that covers `article_repo.py` if one
exists by then (today `article_repo.py` is "not covered" in `pipeline.md`).

Rules and their tests (names to use):

| Rule | Test |
| --- | --- |
| sync makes one document per canonical hash, version only when content >= min | `test_sync_creates_document_and_content_version` |
| same text twice adds no version; changed text adds one and keeps the old | `test_sync_versions_only_on_text_change` |
| re-collected hash reuses its document and updates `article_id` | `test_recollected_article_reuses_document` |
| prune archives before delete, same transaction; dry run writes nothing | `test_prune_archives_rows_before_delete`, `test_prune_dry_run_does_not_archive` |
| no delete path except purge touches archive rows | `test_prune_and_evidence_purge_keep_archive_rows` |
| purge: dry run by default, `--apply` deletes only the selection | `test_archive_purge_dry_run_and_apply` |
| no web, API or MCP module imports the archive | `test_archive_not_imported_by_web_or_mcp` |
| window and `--all`; `--no-download` makes no request | `test_capture_window_and_seed_make_no_requests` |
| reuse of an extracted daily-publish page without a request | `test_capture_reuses_daily_publish_page` |
| downloaded extracted page becomes a `source_page` version | `test_capture_downloads_and_archives_page` |
| permanent issues give up at once | `test_capture_gives_up_on_permanent_issues` |
| other failures follow the retry schedule, then give up | `test_capture_retry_schedule_then_gives_up` |
| retry deletes only the archive cache entry | `test_capture_retry_clears_only_archive_cache` |
| caps per run, per host, and max seconds | `test_capture_respects_caps_and_time` |
| outage does not count as an attempt | `test_capture_outage_keeps_attempts` |
| raw page dirs older than keep days are deleted | `test_capture_deletes_old_raw_pages` |
| summary line fields and coverage | `test_capture_summary_reports_coverage` |
| job script: lock, timeout, always exit 0, no effect on other jobs | `test_archive_job_script_is_isolated` |
| timer installed at 03:00 UTC with its limit | `test_install_timers_includes_archive` (in `tests/unit/test_daily_timers.py`) |
| migration upgrade and downgrade | `test_article_archive_migration_round_trip` (pattern of `tests/unit/test_daily_signals_migration.py`) |

## Next spec: A2 backfill (estimate only)

- Scope: documents outside the window still `pending` after the seed: about 4050 today (7079 minus
  3030 with text), mostly July-September 2026 (full text 26-33% then). Known lost causes first
  excluded: openai.com (231 articles, 403), and hosts that failed every fetch-time extraction
  (medium.com, becominghuman.ai: `RuntimeError` in the fetch log).
- Mechanism: the same `archive capture` with `--all` and download on, run in chunks of
  `ARCHIVE_MAX_DOWNLOADS` on a separate window (for example 05:00 UTC) under the host lock, or a
  one-off operator run; raw page dirs deleted right after extraction to cap disk (4000 x 0.86 MB
  would be 3.4 GB).
- Time: per-host pacing dominates; about 140 hosts in two weeks of articles, a few hosts carry most
  rows; at 4 parallel downloads and 1 s per host, roughly 1-3 hours in total, 5-15 nightly chunks.
- Output: per-host success report and a sample quality review (backlog A2).

## Project Structure

```text
specs/016-article-archive/        spec.md, plan.md, tasks.md, records/
src/app/core/archive/             __init__.py, capture.py, capture.md
src/app/storage/archive.py        ArchiveRepo: upsert, add_version, due, record_result, purge, status, size
src/app/storage/models_sql.py     ArchiveDocument, ArchiveText
src/app/storage/migrations/versions/<rev>_add_article_archive.py
src/app/storage/article_repo.py   prune_older_than archives first
src/app/cli/main.py               `archive` Typer group: capture, status, purge
scripts/run_daily_archive_job.sh  lock + timeout + capture, exit 0
scripts/install_daily_timers.sh   adds the archive unit and timer (03:00 UTC, 3600 s)
docs/deploy.md                    operator commands (seed, status, purge)
tests/unit/test_article_archive.py, test_archive_capture.py; tests/unit/test_deepseek_digest.py (job scripts)
```

**Structure Decision**: a new `core/archive` package and a `storage/archive.py` repository, the
same split as daily signals; no change to the ingestion pipeline.

## Complexity Tracking

| Choice | Why | Simpler alternative rejected because |
| --- | --- | --- |
| Separate timer instead of a step in fetch/digest scripts | full failure isolation, reuse of digest downloads | a step would share and risk the 4-hour budget and exit status of those jobs |
| Two tables instead of one | per-document state and retry vs. append-only versions | one table would repeat metadata per version and mix state with history |
