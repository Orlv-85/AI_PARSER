# Tasks: Fetch Pipeline Optimization (PostgreSQL)

**Input**: Design documents from `.specify/specs/002-fetch-pipeline-optimization/`  
**Prerequisites**: `spec.md`, `plan.md`  
**Tests**: Required (user explicitly requested strong validation; repo-wide lint/tests required before merge)  
**Organization**: Grouped by user story/optimization slice for incremental delivery and safe rollout

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: `US1`, `US2`, ... maps to spec user stories
- Include exact file paths

## Phase 1: Baseline & Safety Rails (Shared Infrastructure)

**Purpose**: Add measurement and feature flags before changing behavior.

- [ ] T001 [P] [US4] Add fetch optimization settings/flags to `src/app/config/settings.py` (conditional fetch toggles, HTML link caps, HTML early-stop threshold, batch upsert toggle, httpx pool limits).
- [ ] T002 [P] [US4] Add source-level performance metric event schema/helpers in `src/app/core/pipeline.py` (or new helper module under `src/app/core/`).
- [ ] T003 [US4] Extend run summary logging in `src/app/core/pipeline.py` with optimization counters (not-modified hits, skipped-known-html, early-stop hits).
- [ ] T004 [P] [US4] Add unit tests for new settings defaults/parsing in `tests/unit/test_settings.py`.
- [ ] T005 [US4] Add benchmark/measurement script stub (or documented command) in `scripts/` to capture before/after fetch metrics consistently.

**Checkpoint**: Pipeline emits enough data to evaluate subsequent optimization slices safely.

---

## Phase 2: User Story 1 - Stable Fast Update Runs via HTTP Connection Reuse (Priority: P1) 🎯 MVP Slice A

**Goal**: Remove avoidable network overhead by reusing HTTP connections.

**Independent Test**: Run repeated fetch requests in tests/mocks and verify client reuse behavior, plus no regressions in retries/rate limiting.

### Tests for User Story 1 ⚠️

- [ ] T006 [P] [US1] Add unit tests for `Fetcher` client lifecycle/reuse in `tests/unit/test_fetcher.py`.
- [ ] T007 [P] [US1] Add unit tests for retry + rate-limit behavior under pooled client in `tests/unit/test_fetcher.py`.

### Implementation for User Story 1

- [ ] T008 [US1] Refactor `src/app/ingest/fetcher.py` to reuse `httpx.Client` (per `Fetcher` instance) with configurable connection limits/timeouts.
- [ ] T009 [US1] Ensure proper client cleanup semantics (context manager or explicit close) in `src/app/ingest/fetcher.py` and `src/app/core/pipeline.py`.
- [ ] T010 [US1] Wire new HTTP pool limit settings into `Fetcher` construction in `src/app/core/pipeline.py`.
- [ ] T011 [US1] Add structured source request-count/timing logging in `src/app/ingest/fetcher.py` or `src/app/core/pipeline.py`.

**Checkpoint**: Same behavior, lower network overhead, observable request timings.

---

## Phase 3: User Story 2 - Conditional Fetch for Unchanged Sources (Priority: P1) 🎯 MVP Slice B

**Goal**: Skip parsing/processing unchanged RSS (and later HTML list pages) using cache validators.

**Independent Test**: Simulate `200 -> stored etag/modified -> 304` sequence and verify skip/non-error behavior and metric counters.

### Tests for User Story 2 ⚠️

- [ ] T012 [P] [US2] Add unit tests for source fetch state persistence/retrieval in `tests/unit/test_source_fetch_state_repo.py`.
- [ ] T013 [P] [US2] Add unit tests for conditional request header construction in `tests/unit/test_fetcher.py`.
- [ ] T014 [P] [US2] Add integration tests for RSS `304 Not Modified` handling in `tests/integration/test_fetch_rss_conditional.py`.

### Implementation for User Story 2

- [ ] T015 [US2] Add persisted source fetch state model/table (e.g., `SourceFetchState`) in `src/app/storage/models_sql.py` and migration support if applicable.
- [ ] T016 [US2] Add repository methods for source fetch state in `src/app/storage/repos.py` (get/update validators and status metadata).
- [ ] T017 [US2] Extend `src/app/ingest/fetcher.py` to send conditional headers (`If-None-Match`, `If-Modified-Since`) and surface `304` distinctly.
- [ ] T018 [US2] Integrate RSS conditional fetch path in `src/app/ingest/rss.py` and `src/app/core/pipeline.py`.
- [ ] T019 [US2] Persist returned `ETag`/`Last-Modified` metadata after successful RSS/list responses in `src/app/core/pipeline.py`.
- [ ] T020 [US2] Emit source-level `not_modified` log events and counters in `src/app/core/pipeline.py`.

**Checkpoint**: Unchanged RSS sources are skipped cheaply and safely.

---

## Phase 4: User Story 3 - HTML Two-Stage Dedup Before Article Fetch (Priority: P1) 🎯 MVP Slice C

**Goal**: Avoid fetching/parsing article pages for known HTML links; apply HTML early-stop and link caps.

**Independent Test**: HTML source with mostly known links should fetch list page only + minimal article pages; counters/logs must reflect skipped-known and early-stop.

### Tests for User Story 3 ⚠️

- [ ] T021 [P] [US3] Add unit tests for HTML link candidate selection (canonical hash + known skip) in `tests/unit/test_html_pipeline_selection.py`.
- [ ] T022 [P] [US3] Add unit tests for HTML known-streak early-stop behavior in `tests/unit/test_pipeline_runtime.py`.
- [ ] T023 [P] [US3] Add integration tests for HTML two-stage fetch reducing article-page requests in `tests/integration/test_fetch_html_two_stage.py`.

### Implementation for User Story 3

- [ ] T024 [US3] Split HTML ingestion in `src/app/ingest/html.py` into:
  - list fetch + link extraction
  - article fetch + article parsing for selected links only.
- [ ] T025 [US3] Add canonical hash precheck path for HTML links in `src/app/core/pipeline.py` using `ArticleRepo.exists_by_canonical_hash` or new batch precheck API.
- [ ] T026 [US3] Add batch known-hash lookup method(s) in `src/app/storage/repos.py` for HTML link sets (e.g., `existing_canonical_hashes(...)`).
- [ ] T027 [US3] Add HTML early-stop threshold + max-links-per-source handling in `src/app/core/pipeline.py` and `src/app/config/settings.py`.
- [ ] T028 [US3] Add structured metrics/logging for HTML link counts, skipped-known count, early-stop reason.

**Checkpoint**: HTML sources stop doing most useless expensive work.

---

## Phase 5: User Story 5 - Postgres Batch Upsert Persistence (Priority: P2)

**Goal**: Reduce DB round-trips and CPU/latency in persistence using bulk upsert.

**Independent Test**: Batch persist mixed new/existing items with correct row counts and counters, and no duplicate canonical hashes.

### Tests for User Story 5 ⚠️

- [ ] T029 [P] [US5] Add unit tests for batch upsert result accounting in `tests/unit/test_article_repo_batch_upsert.py`.
- [ ] T030 [P] [US5] Add integration tests against Postgres for `ON CONFLICT` semantics in `tests/integration/test_article_upsert_postgres.py`.
- [ ] T031 [P] [US5] Add regression tests confirming duplicate and new counters match previous semantics in `tests/unit/test_pipeline_runtime.py`.

### Implementation for User Story 5

- [ ] T032 [US5] Add Postgres-specific bulk upsert method(s) to `src/app/storage/repos.py` (feature-flagged fallback to current per-item path).
- [ ] T033 [US5] Refactor `src/app/core/pipeline.py` to use batch persistence for source items where enabled.
- [ ] T034 [US5] Preserve/validate counter semantics (`fetched`, `new`, `duplicates`, `errors`) and log summaries.
- [ ] T035 [US5] Add runtime/setting toggle for batch upsert in `src/app/config/settings.py`.

**Checkpoint**: DB persistence cost reduced without dedup regressions.

---

## Phase 6: User Story 4 - Tuning, Visibility, and Operational Controls (Priority: P2)

**Goal**: Make optimization tunable and operationally safe on small VPS.

**Independent Test**: Toggle settings in env/UI and confirm behavior/logging changes without code changes.

### Tests for User Story 4 ⚠️

- [ ] T036 [P] [US4] Add tests for settings propagation to web update runtime in `tests/unit/test_web_update_settings.py`.
- [ ] T037 [P] [US4] Add tests for structured optimization events (schema/fields) in `tests/unit/test_pipeline_runtime.py`.

### Implementation for User Story 4

- [ ] T038 [US4] Extend `src/app/web/models.py` and `src/app/web/settings_store.py` to include new optimization runtime knobs (as applicable).
- [ ] T039 [US4] Update `src/app/web/app.py` and UI template (`src/app/web/index.html`) to display/accept safe tuning fields (optional if deferred behind hidden config).
- [ ] T040 [US4] Document recommended production defaults and staged rollout steps in `README.md`.
- [ ] T041 [US4] Add operational runbook section (metrics to watch, rollback toggles) in `.specify/specs/002-fetch-pipeline-optimization/plan.md` or `README.md`.

**Checkpoint**: Ops can tune and validate safely in production.

---

## Phase 7: Optional Advanced Optimizations (P3 / deferred but planned)

**Purpose**: Additional performance gains after P1/P2 are stable.

- [ ] T042 [P] [US2] Add HTML list-page conditional fetch support in `src/app/ingest/html.py` + state persistence in `src/app/storage/repos.py`.
- [ ] T043 [P] [US3] Evaluate `selectolax` for HTML link extraction hot path and benchmark vs `lxml` (`src/app/ingest/html.py`, `tests/benchmarks/` if added).
- [ ] T044 [P] [US1] Add source-type execution profiles (RSS-fast vs HTML-heavy) in `src/app/core/pipeline.py` and `src/app/config/settings.py`.
- [ ] T045 [US1] Prototype queue/offloaded worker mode (e.g., RQ) for web-triggered updates in `src/app/web/service.py` / new worker module (design spike only unless approved).

---

## Final Quality Gates (mandatory before merge)

- [ ] T046 Run `make lint PYTHON=./venv1/bin/python` (repo-wide) and record result.
- [ ] T047 Run `./venv1/bin/pytest` (repo-wide) and record result.
- [ ] T048 Run target performance benchmark/baseline comparison and attach before/after numbers to PR/notes.
- [ ] T049 Validate production-safe defaults (`full-text off`, conservative concurrency, feature flags) in `README.md` / deploy scripts.

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 (Baseline & Safety Rails): no dependencies; starts immediately.
- Phase 2 (HTTP pooling): depends on Phase 1 metrics/flags.
- Phase 3 (Conditional fetch): depends on Phase 1; can begin after Phase 2 if fetcher API changes are stabilized.
- Phase 4 (HTML two-stage): depends on Phase 1 and ideally Phase 2; independent from batch upsert.
- Phase 5 (Batch upsert): depends on Phase 1 and pipeline integration points; can run after Phase 4 selection logic is stable.
- Phase 6 (Ops tuning/visibility): after at least one optimization slice is implemented.
- Phase 7 (Optional): after P1/P2 slices are validated.

### User Story Dependencies

- **US1 (P1)**: foundational for network efficiency; should land first.
- **US2 (P1)**: depends on fetcher/header support and source-state persistence.
- **US3 (P1)**: depends on dedup precheck and settings; delivers biggest HTML savings.
- **US5 (P2)**: can be introduced after behavior is stabilized to avoid mixing semantics and performance bugs.
- **US4 (P2)**: spans all slices, but core observability starts in Phase 1.

## Parallel Opportunities

- T001/T002/T004 can run in parallel.
- T006/T007 can run in parallel before fetcher refactor.
- T012/T013/T014 can run in parallel for conditional fetch slice.
- T021/T022/T023 can run in parallel for HTML two-stage slice.
- T029/T030/T031 can run in parallel for batch upsert validation.
- T046/T047 can run in parallel if CI/local resources permit (or sequentially on constrained machine).

## Implementation Strategy

### MVP Performance First (recommended)

1. Phase 1 (metrics/flags)
2. Phase 2 (HTTP pooling)
3. Phase 3 (RSS conditional fetch)
4. Phase 4 (HTML two-stage dedup + early-stop)
5. Stop, benchmark, validate production behavior

This already delivers major wins without DB semantic changes.

### Incremental Delivery

1. Deliver network-side savings (pooling + conditional RSS)
2. Deliver HTML workload reduction (two-stage + early-stop)
3. Deliver DB-side efficiency (batch Postgres upsert)
4. Tune and harden with observability

## Notes

- Keep all risky optimizations behind feature flags / conservative defaults.
- Preserve fail-soft behavior per source.
- Do not increase concurrency as a first-line optimization; remove wasted work first.
- Measure before/after every slice to avoid “optimizations” that move bottlenecks instead of reducing them.

