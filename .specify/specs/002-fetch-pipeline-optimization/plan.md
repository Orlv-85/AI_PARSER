# Implementation Plan: Fetch Pipeline Optimization (PostgreSQL)

**Branch**: `002-fetch-pipeline-optimization` | **Date**: 2026-02-23 | **Spec**: `.specify/specs/002-fetch-pipeline-optimization/spec.md`  
**Input**: Feature specification from `.specify/specs/002-fetch-pipeline-optimization/spec.md`

## Summary

Optimize the ingestion pipeline to remove avoidable work before scaling concurrency:

1. Reuse HTTP connections (`httpx.Client` pooling) during fetch runs.
2. Add conditional HTTP fetch for RSS (and HTML list pages when possible) using persisted source fetch state (`ETag`, `Last-Modified`).
3. Split HTML ingestion into a two-stage flow so dedup happens before article-page fetch/extraction.
4. Add HTML early-stop on known-link streak.
5. Improve Postgres persistence using bulk upsert (`ON CONFLICT`) while preserving counters and dedup guarantees.
6. Add metrics/logging and staged rollout toggles to validate impact safely on production.

This sequence prioritizes highest ROI / lowest-risk changes first, then introduces database and architectural improvements.

## Technical Context

**Language/Version**: Python 3.14.x  
**Primary Dependencies**: FastAPI, Typer, SQLAlchemy, httpx, feedparser, lxml, trafilatura, readability-lxml  
**Storage**: PostgreSQL (production), SQLAlchemy ORM  
**Testing**: pytest, pytest-cov, mypy, ruff, pylint  
**Target Platform**: Linux VPS (Docker Compose, Caddy reverse proxy)  
**Project Type**: Single Python app (CLI + Web API/UI)  
**Performance Goals**:
- Reduce median fetch runtime >=40%
- Reduce unchanged-run HTTP requests >=50%
- Prevent ingestion-driven app degradation/`502` on production VPS
**Constraints**:
- Must preserve dedup correctness
- Fail-soft per source
- No unsafe concurrency spikes on small VPS
- Backward-compatible defaults with safe feature flags/tunables
**Scale/Scope**:
- Tens to low hundreds of sources
- Mixed RSS + HTML sources
- Predominantly repeated polling with mostly unchanged results between runs

## Constitution Check

### Pre-Phase-0 Gate (Pass)

- Spec exists and includes measurable outcomes: PASS
- Testability and independent user stories defined: PASS
- Observability and rollback/flags considered: PASS
- Production safety prioritized over raw throughput tuning: PASS

### Re-check After Design (Target)

- All risky optimizations behind settings flags or conservative defaults
- Metrics available before/after each optimization slice
- Rollout can stop after any P1 slice with value delivered

## Research & External References (applied to this plan)

The plan uses well-supported primitives and documented behavior:

- HTTPX persistent clients and connection pooling:
  - https://www.python-httpx.org/advanced/clients/
  - https://www.python-httpx.org/advanced/resource-limits/
- HTTP conditional requests and `304 Not Modified` semantics:
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-None-Match
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-Modified-Since
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/304
- feedparser HTTP cache validators (`etag`, `modified`) support:
  - https://feedparser.readthedocs.io/en/main/http/
  - https://feedparser.readthedocs.io/en/releases/reference-etag.html
  - https://feedparser.readthedocs.io/en/releases/reference-modified.html
- SQLAlchemy/PostgreSQL upsert patterns:
  - https://docs.sqlalchemy.org/en/21/dialects/postgresql.html
- Optional faster HTML parsing for link extraction (`selectolax`):
  - https://github.com/rushter/selectolax
- Optional queue-based workload isolation (future phase):
  - https://github.com/rq/rq

## Current-State Bottlenecks (Code-Specific)

1. `src/app/ingest/fetcher.py`
- `Fetcher.request()` creates a new `httpx.Client` per request.
- Effect: lost keep-alive / pooling, repeated TCP+TLS overhead.

2. `src/app/ingest/html.py`
- HTML article pages are fetched and parsed before dedup decisions.
- Effect: expensive repeated downloads and extraction for already-known links.

3. `src/app/storage/repos.py` + `src/app/core/pipeline.py`
- Per-item existence checks and insert/update path increase DB round-trips.
- Effect: higher latency on Postgres under larger batches.

4. Observability gap
- Run-level counters exist, but source-stage timing/skip reasons are limited.
- Effect: hard to validate optimization impact and tune safely.

## Design Overview (Target Architecture)

### A. Fetch Execution Layer

- Introduce a reusable HTTP client lifecycle for fetch runs (or per worker thread).
- Configure HTTPX limits for connection pooling and keepalive.
- Maintain per-source rate limiting behavior.

### B. Source Fetch State Persistence

- Store cache validators and source fetch metadata in DB (or source-state table):
  - `source_id`
  - `etag`
  - `last_modified`
  - `last_checked_at`
  - `last_status_code`
  - `not_modified_count` (optional metric)
- Used by RSS and HTML list-page conditional fetches.

### C. Two-Stage HTML Ingestion

1. Stage 1 (cheap):
- Fetch list page
- Extract candidate links
- Canonicalize/hash links
- Batch-check known hashes
- Apply HTML known-streak early-stop / max-links limits

2. Stage 2 (expensive):
- Fetch article pages only for selected links
- Extract title/content
- Persist results

### D. Persistence Layer (Postgres-Optimized)

- Add batch insert/upsert path for articles using `ON CONFLICT (url_canonical_hash)`.
- Preserve existing semantics for score/rank updates on duplicates.
- Keep fallback path for compatibility / rollout flag.

### E. Observability & Tuning

- Per-source structured events for:
  - `source_fetch_started`
  - `source_fetch_not_modified`
  - `source_html_links_extracted`
  - `source_html_known_skipped`
  - `source_early_stop`
  - `source_persist_batch_summary`
  - `source_fetch_finished`
- Run summary extended with optimization counters.

## Rollout Strategy (Incremental, Safe)

### Slice 1 (P1, low risk, high ROI)
- HTTPX client pooling
- Metrics baseline + source-level timings
- No behavior change to dedup semantics

### Slice 2 (P1)
- RSS conditional fetch (`ETag` / `Last-Modified`)
- Persist source fetch state
- `304` support and logging

### Slice 3 (P1, biggest HTML impact)
- HTML two-stage flow
- Known-hash precheck before article fetch
- HTML early-stop + max link cap

### Slice 4 (P2)
- Batch Postgres upsert
- Query-count reduction and performance validation

### Slice 5 (P2/P3 optional)
- HTML conditional list-page fetch
- Queue/offloaded ingestion worker mode
- Priority source groups / execution profiles

## Operational Runbook (Phase 6)

### Metrics to watch during rollout

- `fetch_run_duration_seconds` trend per run
- `not_modified_sources` in `fetch_run_finished`
- `skipped_known_html_links` in `fetch_run_finished`
- `early_stop_hits` in `fetch_run_finished`
- per-source `source_fetch_finished` payloads:
  - `fetched_items`
  - `new_items`
  - `duplicate_items`
  - `skipped_known_items`
  - `early_stop_hit`

### Safe rollout order

1. Keep source metrics enabled and compare two to three runs against the same source mix.
2. Validate that unchanged RSS sources produce more `not_modified_sources`.
3. Validate that HTML-heavy runs show higher `skipped_known_html_links` without rising error counts.
4. Enable batch upsert only after network-side improvements are stable.

### Rollback levers

- `article_batch_upsert_enabled=false`
- `fetch_conditional_requests_enabled=false`
- `rss_known_streak_stop=0`
- `html_known_streak_stop=0`
- reduce `html_max_links_per_source`
- reduce `concurrency_limit`

### Success signals

- shorter run duration on repeated polls
- fewer article-page requests for HTML-heavy sources
- stable or lower error counts
- no user-visible `502` or app-health degradation during updates

## Project Structure

### Documentation (this feature)

```text
.specify/specs/002-fetch-pipeline-optimization/
├── spec.md
├── plan.md
└── tasks.md
```

### Source Code (repository root)

```text
src/app/
├── cli/main.py
├── config/
│   ├── settings.py
│   └── sources.py
├── core/
│   ├── pipeline.py
│   └── canonicalize.py
├── ingest/
│   ├── fetcher.py
│   ├── rss.py
│   └── html.py
├── storage/
│   ├── db.py
│   ├── models_sql.py
│   └── repos.py
└── web/
    ├── app.py
    └── service.py

tests/
├── unit/
├── integration/
└── contract/
```

**Structure Decision**: Use the existing single-project Python layout. Changes will concentrate in `ingest/`, `core/pipeline.py`, and `storage/` with additional tests and minimal surface changes to CLI/web.

## Performance Measurement Plan (mandatory before/after each slice)

### Baseline Metrics to Capture

- `fetch_run_duration_seconds`
- Per-source:
  - `source_fetch_duration_seconds`
  - `source_http_requests_total`
  - `source_items_seen_total`
  - `source_items_new_total`
  - `source_items_duplicate_total`
  - `source_items_skipped_known_total`
  - `source_early_stop_hits_total`
  - `source_not_modified_hits_total`
- DB:
  - `article_insert_attempts`
  - `article_conflicts`
  - `article_upserts`
  - (Optional) SQL query count in tests/profiling harness

### Validation Environments

1. Local regression tests (unit/integration)
2. Docker CI (`make lint`, `pytest`)
3. Staging/production-like VPS run on sample source set
4. Controlled production rollout with feature flags

## Testing Strategy

- Unit tests:
  - conditional fetch header/state handling
  - HTML link-stage dedup selection logic
  - HTML early-stop semantics
  - Postgres upsert result/counter mapping
- Integration tests:
  - fetch run with mocked HTTP responses incl. `304`
  - mixed RSS/HTML source behavior and counters
- Performance regression harness:
- repeatable benchmark script on fixed fixtures/source snapshots (optional but recommended)

Benchmark note (completed local fixture run):
- `scripts/bench_html_link_parsers.py` on `tests/fixtures/html/list_page.html` (1000 iterations, Python 3.14.2)
- `lxml`: `0.0413s`
- `selectolax`: `0.0341s`
- observed `selectolax` speedup on the link-extraction hot path: `1.21x`
- Final gates before merge:
  - `make lint PYTHON=./venv1/bin/python`
  - `./venv1/bin/pytest`

## Risks & Mitigations

- **Risk**: HTML early-stop misses late new links on unstable pages  
  **Mitigation**: conservative threshold; feature flag; logging early-stop hits; per-source opt-out.

- **Risk**: Conditional fetch state bugs cause stale data  
  **Mitigation**: fallback to unconditional fetch on parse/header errors; explicit logging; tests for invalid validators.

- **Risk**: Batch upsert changes duplicate/update counters  
  **Mitigation**: golden tests for counters and row counts; staged rollout behind flag.

- **Risk**: Shared HTTP client thread-safety misuse  
  **Mitigation**: scope client lifecycle per fetcher/thread or document safe usage pattern; add tests.

## Out of Scope for This Spec (deferred)

- Full async rewrite of the entire ingestion pipeline
- Distributed worker cluster / Kafka
- Content embeddings / semantic dedup
- Headless browser rendering for JS-heavy sites
