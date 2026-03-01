# Tasks: Source Onboarding and Validation Workflow

**Input**: Design documents from `.specify/specs/003-source-onboarding-management/`  
**Prerequisites**: `spec.md`, `plan.md`  
**Tests**: Required (repo-wide lint/tests before merge; validation flows need unit + integration coverage)  
**Organization**: Grouped by user story / delivery phase

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel
- **[Story]**: `US1`, `US2`, ... maps to spec user stories
- Include exact file paths

## Phase 1: Data Model and Bulk Intake (MVP Foundation)

**Purpose**: Create the DB-backed foundation and raw candidate intake path.

### Tests for Phase 1 ⚠️

- [ ] T001 [P] [US1] Add unit tests for raw URL extraction from plain text and markdown in `tests/unit/test_source_onboarding_parser.py`.
- [ ] T002 [P] [US1] Add unit tests for URL normalization and wrapper rejection in `tests/unit/test_source_onboarding_parser.py`.
- [ ] T003 [P] [US1] Add repository tests for draft candidate creation and exact dedup in `tests/unit/test_source_candidate_repo.py`.

### Implementation for Phase 1

- [ ] T004 [US1] Add onboarding models to `src/app/storage/models_sql.py` (`SourceCandidate`, `SourceImportBatch`, minimal validation fields).
- [ ] T005 [US1] Add onboarding repository methods to `src/app/storage/repos.py` (create batch, insert candidates, reject exact duplicates).
- [ ] T006 [US1] Add parsing/normalization service in `src/app/core/source_onboarding.py` for raw-text URL extraction and canonical candidate creation.
- [ ] T007 [US1] Add CLI entry point in `src/app/cli/main.py` for bulk import of candidate text.
- [ ] T008 [US1] Add minimal API endpoint in `src/app/web/app.py` for posting raw candidate text and creating a `SourceImportBatch`.

**Checkpoint**: A raw text block can become draft candidates in DB with exact duplicates blocked.

---

## Phase 2: Duplicate Heuristics and Live Validation (P1)

**Purpose**: Detect source overlaps and validate candidates before approval.

### Tests for Phase 2 ⚠️

- [ ] T009 [P] [US2] Add unit tests for overlap grouping heuristics in `tests/unit/test_source_onboarding_dedupe.py`.
- [ ] T010 [P] [US3] Add unit tests for RSS candidate validation in `tests/unit/test_source_validation.py`.
- [ ] T011 [P] [US3] Add unit tests for HTML candidate validation and link extraction viability in `tests/unit/test_source_validation.py`.
- [ ] T012 [P] [US3] Add integration tests for end-to-end validation status persistence in `tests/integration/test_source_validation_flow.py`.

### Implementation for Phase 2

- [ ] T013 [US2] Add overlap/duplicate grouping logic in `src/app/core/source_onboarding.py` (same-host family, path-prefix, topic-page heuristics).
- [ ] T014 [US3] Add validation runner in `src/app/core/source_onboarding.py` using `src/app/ingest/fetcher.py`, `src/app/ingest/rss.py`, and `src/app/ingest/html.py`.
- [ ] T015 [US3] Persist validation results/status in `src/app/storage/repos.py` and `src/app/storage/models_sql.py`.
- [ ] T016 [US3] Add API/CLI actions to trigger validation for a batch or selected candidate IDs (`src/app/web/app.py`, `src/app/cli/main.py`).
- [ ] T017 [US2] Add duplicate/overlap query APIs in `src/app/storage/repos.py` for UI review.

**Checkpoint**: Candidates can be validated and grouped before approval.

---

## Phase 3: Review UI and Approval Workflow (P1/P2)

**Purpose**: Give operators a usable review queue to approve, reject, merge, or edit candidates.

### Tests for Phase 3 ⚠️

- [ ] T018 [P] [US4] Add API tests for review actions (`approve`, `reject`, `mark_duplicate`, `edit`) in `tests/unit/test_web_source_onboarding_api.py`.
- [ ] T019 [P] [US4] Add service-level tests for approval transitions in `tests/unit/test_source_onboarding_service.py`.
- [ ] T020 [P] [US4] Add UI response/model tests for candidate list filtering and batch summary in `tests/unit/test_web_source_onboarding_view.py`.

### Implementation for Phase 3

- [ ] T021 [US4] Add review models / request schemas to `src/app/web/models.py`.
- [ ] T022 [US4] Add onboarding review endpoints in `src/app/web/app.py` (list drafts, get batch summary, approve/reject/edit/merge actions).
- [ ] T023 [US4] Add onboarding service orchestration in `src/app/web/service.py` or `src/app/core/source_onboarding.py`.
- [ ] T024 [US4] Add onboarding review UI in `src/app/web/index.html` or a dedicated template under `src/app/web/`.
- [ ] T025 [US4] Wire approval flow so approved candidates become active fetch sources without manual `sources.yaml` edits.

**Checkpoint**: Operator can complete an onboarding batch from the web UI.

---

## Phase 4: YAML Bootstrap and Export Interop (P2)

**Purpose**: Preserve compatibility while shifting source-of-truth to DB.

### Tests for Phase 4 ⚠️

- [ ] T026 [P] [US5] Add tests for importing `sources.yaml` into DB-backed source records in `tests/unit/test_sources_bootstrap_import.py`.
- [ ] T027 [P] [US5] Add tests for deterministic YAML export in `tests/unit/test_sources_export.py`.

### Implementation for Phase 4

- [ ] T028 [US5] Add bootstrap import path from `sources.yaml` in `src/app/config/sources.py` and/or a new onboarding bootstrap module.
- [ ] T029 [US5] Add deterministic approved-source export to YAML snapshot in `src/app/core/source_onboarding.py` or a dedicated exporter module.
- [ ] T030 [US5] Update `scripts/sources_onboarding_helper.py` to support DB-backed candidate review/validation commands where appropriate.
- [ ] T031 [US5] Document DB-primary / YAML-secondary source management in `README.md`.

**Checkpoint**: Existing YAML workflows can coexist with DB-backed onboarding.

---

## Phase 5: Batch-Specific Seed Rules for the Provided QA/AI Source Set (Optional but immediately useful)

**Purpose**: Encode practical heuristics discovered from the provided 50-source QA/AI batch.

- [ ] T032 [P] [US2] Add fixture(s) for the provided AI-in-testing batch in `tests/fixtures/source_batches/qa_ai_sources.txt`.
- [ ] T033 [P] [US2] Add classification tests for search-wrapper URLs, broad media pages, and same-vendor overlaps in `tests/unit/test_source_onboarding_batch_rules.py`.
- [ ] T034 [US2] Add batch heuristics/rules for rejecting search-wrapper URLs and flagging topic-page candidates in `src/app/core/source_onboarding.py`.
- [ ] T035 [US3] Add a reporting command or API summary for batch review outcomes in `src/app/cli/main.py` or `src/app/web/app.py`.

**Checkpoint**: The current real-world batch can be ingested, triaged, and reviewed predictably.

---

## Final Quality Gates (mandatory before merge)

- [ ] T036 Run `make lint PYTHON=./venv1/bin/python` (repo-wide) and record result.
- [ ] T037 Run `./venv1/bin/pytest` (repo-wide) and record result.
- [ ] T038 Run onboarding-specific integration validation against a representative candidate batch and record outcomes.
- [ ] T039 Confirm no regression in existing fetch/update workflows when approved sources are loaded from DB.

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 must land first.
- Phase 2 depends on Phase 1 draft persistence and parsing.
- Phase 3 depends on Phase 2 validation and duplicate grouping.
- Phase 4 depends on stable approval semantics from Phase 3.
- Phase 5 can begin once Phase 1 and Phase 2 parsing/validation rules exist.

### Parallel Opportunities

- T001/T002/T003 can run in parallel.
- T009/T010/T011 can run in parallel.
- T018/T019/T020 can run in parallel.
- T026/T027 can run in parallel.
- T032/T033 can run in parallel.

## Implementation Strategy

### Recommended MVP

1. Phase 1 (bulk intake + DB draft storage)
2. Phase 2 (validation + duplicate heuristics)
3. Stop and validate the provided 50-source batch
4. Phase 3 (review UI + approvals)
5. Phase 4 (YAML interop)

This delivers immediate operational value before building the full lifecycle.

## Notes

- The provided 50-source batch should be treated as the first real acceptance fixture for this feature.
- Search-wrapper links from that batch should be explicitly rejected by code, not manually corrected ad hoc.
- The fetch pipeline should continue consuming approved sources only; draft candidates must stay isolated until approved.
