# Feature Specification: Fetch Pipeline Optimization (PostgreSQL)

**Feature Branch**: `002-fetch-pipeline-optimization`  
**Created**: 2026-02-23  
**Status**: Draft  
**Input**: User description: "ускорить fetch pipeline, оптимизировать архитектурно, убрать лишнюю работу, сделать подробную спеку/план/tasks под формат .specify"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stable Fast Update Runs on Production VPS (Priority: P1)

As an operator, I want update runs to complete significantly faster and with lower resource spikes, so the app and server do not degrade during ingestion.

**Why this priority**: This directly addresses production incidents (`502`, container degradation, long-running updates, server overload).

**Independent Test**: Run `ai-news fetch --once` on a representative source set and compare baseline vs optimized run metrics (duration, HTTP requests, DB writes, CPU/RAM peak).

**Acceptance Scenarios**:

1. **Given** a production-like Postgres dataset with many existing articles, **When** a fetch run executes, **Then** the pipeline avoids reprocessing most already-known RSS/HTML items and finishes faster than baseline.
2. **Given** the web UI is serving requests during an update run, **When** fetch is running, **Then** the web app remains responsive and does not return `502` due to ingestion overload alone.

---

### User Story 2 - Efficient Re-fetch of Mostly Unchanged Sources (Priority: P1)

As the ingestion pipeline, I want to skip downloading/parsing unchanged source feeds/pages whenever possible, so repeated runs consume less network and CPU.

**Why this priority**: Repeated polling of unchanged sources is a large avoidable cost and happens continuously.

**Independent Test**: Execute two back-to-back runs against the same enabled sources and verify the second run performs fewer network transfers and parsing steps using conditional fetch metadata / not-modified handling.

**Acceptance Scenarios**:

1. **Given** an RSS source that returns `ETag` or `Last-Modified`, **When** a subsequent run executes without feed changes, **Then** the system records and uses conditional headers and treats `304` as a non-error skip.
2. **Given** an unchanged HTML list page (if supported by source response headers), **When** a subsequent run executes, **Then** the system can skip downstream link/article processing for that source.

---

### User Story 3 - Cheap Handling of HTML Sources with Many Old Links (Priority: P1)

As the ingestion pipeline, I want to avoid fetching full article pages for HTML links that are already known, so HTML sources stop dominating runtime.

**Why this priority**: HTML sources are the heaviest path because they fetch list page + many article pages + text extraction before deduplication.

**Independent Test**: Use an HTML source fixture/list containing mostly known links and verify only new links trigger article-page fetch + extraction.

**Acceptance Scenarios**:

1. **Given** an HTML source list page with 50 links where 45 are already known, **When** the pipeline runs, **Then** at most the new links (plus bounded lookahead, if configured) trigger article-page downloads.
2. **Given** a sequence of consecutive known HTML links, **When** the configured known-streak stop threshold is reached, **Then** the pipeline stops processing further links for that source.

---

### User Story 4 - Safe Performance Tuning and Observability (Priority: P2)

As an operator/developer, I want clear per-source/per-stage metrics and tunable limits, so I can adjust concurrency and validate optimization impact safely.

**Why this priority**: Performance changes without visibility are hard to validate and easy to regress.

**Independent Test**: Run fetch and inspect structured logs / metrics summary for network, parse, DB, skipped-not-modified, and early-stop counters.

**Acceptance Scenarios**:

1. **Given** a completed fetch run, **When** logs are inspected, **Then** each source includes counters/timings for fetch, parsed items, skipped-known, early-stop hits, and errors.
2. **Given** runtime settings for concurrency and optimization flags, **When** they are changed, **Then** behavior changes accordingly without code edits.

---

### User Story 5 - Postgres-Friendly Bulk Persistence (Priority: P2)

As the ingestion pipeline, I want to persist articles using batched Postgres upserts, so DB round-trips and lock contention are reduced under load.

**Why this priority**: Current per-item existence checks + inserts are expensive at scale.

**Independent Test**: Run a controlled insert/update workload and compare query counts and runtime vs per-item `SELECT + INSERT/UPDATE`.

**Acceptance Scenarios**:

1. **Given** a batch of articles with mixed new/existing canonical hashes, **When** persistence executes, **Then** the system performs bulk insert/upsert with correct dedup semantics and returns accurate counters.
2. **Given** rank/relevance/freshness values for existing rows, **When** a duplicate item is processed, **Then** the configured upsert policy updates the intended fields without duplicating rows.

## Edge Cases

- Sources that reorder RSS entries (new item appears after known streak).
- Sources that omit `ETag`/`Last-Modified` or send invalid header values.
- HTML pages with unstable selectors or duplicate links.
- Canonicalization differences causing false “new” detections.
- Partial failures (list page fetched, some article pages timeout).
- Postgres transient errors during bulk upsert; run must fail-soft per source where possible.
- Overlapping update runs (manual/UI + cron/manual CLI).
- Very large feeds or HTML link lists causing memory growth if fully buffered.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST collect baseline per-run and per-source performance metrics (duration, request counts, fetched items, parsed items, new/duplicate counts, errors) before and after optimization rollout.
- **FR-002**: System MUST reuse HTTP connections during a fetch run (connection pooling) instead of creating a new HTTP client per request.
- **FR-003**: System MUST support conditional HTTP requests (`ETag` and/or `Last-Modified`) for RSS sources and treat `304 Not Modified` as a successful no-op fetch.
- **FR-004**: System SHOULD support conditional HTTP requests for HTML list pages when source responses provide cache validators.
- **FR-005**: System MUST persist per-source fetch state needed for conditional requests and optimization decisions (e.g., `etag`, `last_modified`, `last_checked_at`, `last_status_code`).
- **FR-006**: System MUST perform HTML ingestion in two stages: (a) fetch list page and extract candidate links, (b) fetch article pages only for links selected after dedup/filters.
- **FR-007**: System MUST avoid full article page downloads for HTML links that are already known by canonical hash, except where an explicit fallback path is required.
- **FR-008**: System MUST support an HTML known-streak early-stop threshold similar to RSS early-stop, configurable via settings/env.
- **FR-009**: System MUST keep existing correctness guarantees for canonical URL deduplication (no duplicate article rows for same canonical hash).
- **FR-010**: System MUST preserve fail-soft behavior: one source failure MUST NOT abort the entire fetch run.
- **FR-011**: System MUST expose optimization controls via settings/env (enable/disable flags, thresholds, per-type concurrency, limits).
- **FR-012**: System SHOULD implement Postgres-optimized bulk insert/upsert (`ON CONFLICT`) for article persistence to reduce per-item DB round-trips.
- **FR-013**: System MUST preserve accurate `new`, `duplicates`, `errors`, and `fetched` counters after optimization changes.
- **FR-014**: System MUST emit structured logs for optimization decisions (`not_modified`, `early_stop`, `skipped_known_html`, `bulk_upsert_summary`).
- **FR-015**: System MUST include regression tests covering RSS/HTML early-stop, conditional fetch handling, and persistence semantics.

### Key Entities *(include if feature involves data)*

- **SourceFetchState**: Per-source persisted fetch metadata used for conditional requests and skip decisions (e.g., `etag`, `last_modified`, `last_status_code`, timestamps).
- **FetchSourceMetrics**: Per-source runtime counters/timers for observability (`http_requests`, `items_seen`, `items_inserted`, `items_skipped_known`, `early_stop_reason`, durations).
- **PersistenceBatchResult**: Aggregated result of batch insert/upsert for one source (`new_count`, `updated_count`, `duplicate_count`, `conflicts`, `errors`).
- **ExecutionProfile**: Runtime tuning parameters for fetch behavior (global concurrency, RSS/HTML concurrency, per-source limits, early-stop thresholds, conditional-fetch toggles).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Median `fetch --once` runtime on a representative production-like source set is reduced by at least **40%** versus pre-optimization baseline.
- **SC-002**: P95 fetch runtime is reduced by at least **30%** versus baseline during normal source availability.
- **SC-003**: On consecutive runs with mostly unchanged sources, total outbound HTTP requests are reduced by at least **50%** versus baseline.
- **SC-004**: For HTML-heavy sources with mostly known links, article-page fetch count is reduced by at least **70%** versus baseline.
- **SC-005**: Web app health endpoint and news listing remain responsive during updates (no ingestion-caused `502` under validated VPS limits in staged testing).
- **SC-006**: Dedup correctness remains intact: repeated runs create no duplicate rows for the same canonical URL hash.
- **SC-007**: New observability events/counters are present in logs for at least 95% of processed sources in a test run.

