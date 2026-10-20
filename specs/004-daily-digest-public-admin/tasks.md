# Tasks: Public Daily Digest and Admin Separation

**Input**: Design documents from `specs/004-daily-digest-public-admin/`  
**Prerequisites**: `spec.md`, `plan.md`  
**Tests**: Required (unit tests for route protection, digest API/storage, and public/admin page rendering; repo-wide lint/tests before merge)  
**Organization**: Grouped by user story / delivery phase

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel
- **[Story]**: `US1`, `US2`, ... maps to spec user stories
- Include exact file paths

## Phase 1: Digest Data Model and Public API Contract

**Purpose**: Create the storage model and HTTP contract for date-scoped link feeds and digest retrieval/submission.

### Tests for Phase 1 ⚠️

- [ ] T001 [P] [US3] Add repository tests for digest report create/replace/read flows in `tests/unit/test_news_digest_repo.py`.
- [ ] T002 [P] [US3] Add API tests for `GET /api/news/links` date filtering in `tests/unit/test_web_digest_api.py`.
- [ ] T003 [P] [US3] Add API tests for `POST /api/news/digests` and `GET /api/news/digests` in `tests/unit/test_web_digest_api.py`.

### Implementation for Phase 1

- [ ] T004 [US3] Add digest storage models (`NewsDigestReport`, `NewsDigestGroup`, `NewsDigestItem`) in `src/app/storage/models_sql.py`.
- [ ] T005 [US3] Add digest repository methods (save/replace/get) in `src/app/storage/repos.py`.
- [ ] T006 [US3] Add web request/response schemas for digest and link-feed payloads in `src/app/web/models.py`.
- [ ] T007 [US3] Add public digest APIs in `src/app/web/app.py` for:
  - `GET /api/news/links`
  - `POST /api/news/digests`
  - `GET /api/news/digests`

**Checkpoint**: External clients can fetch links for a date and store/read a digest for that date.

---

## Phase 2: Public Digest Web Surface

**Purpose**: Make the public digest the default landing page and render stored grouped reports.

### Tests for Phase 2 ⚠️

- [ ] T008 [P] [US1] Add page tests for unauthenticated `/` digest rendering and empty state in `tests/unit/test_web_public_digest.py`.
- [ ] T009 [P] [US1] Add UI-shell tests for date selection and public digest elements in `tests/unit/test_web_app.py`.

### Implementation for Phase 2

- [ ] T010 [US1] Add a dedicated public digest template (likely `src/app/web/digest.html`) with:
  - default "today" selection
  - selected-date loading
  - grouped digest rendering
  - clean empty state
- [ ] T011 [US1] Update `src/app/web/app.py` so `/` serves the public digest page instead of the admin shell.
- [ ] T012 [US1] Add client-side fetch/render logic for loading digest content by date in the public template.

**Checkpoint**: Public visitors land on a usable digest page by default.

---

## Phase 3: Admin Console Relocation and Route Protection

**Purpose**: Move operator tools under `/admin` and harden public/private boundaries.

### Tests for Phase 3 ⚠️

- [ ] T013 [P] [US2] Add route protection tests for unauthenticated `/admin` and public `/` in `tests/unit/test_web_app.py`.
- [ ] T014 [P] [US2] Add auth middleware boundary tests for public digest APIs vs protected admin APIs in `tests/e2e/test_auth_e2e.py`.
- [ ] T015 [P] [US2] Add UI-shell tests confirming admin controls only appear under `/admin` in `tests/unit/test_web_app.py`.

### Implementation for Phase 3

- [ ] T016 [US2] Move the existing admin shell rendering to `/admin` in `src/app/web/app.py`.
- [ ] T017 [US2] Keep the existing login page and session gate, but update middleware/public-route logic in `src/app/web/app.py` and `src/app/web/auth.py` so:
  - digest page and selected digest APIs stay public
  - admin shell and admin APIs stay protected
- [ ] T018 [US2] Ensure existing update/news-tools/onboarding features still render correctly inside the `/admin` shell.

**Checkpoint**: Admin tools remain private and the public digest remains open.

---

## Phase 4: Digest Submission Semantics and Publication Flow

**Purpose**: Finalize the write path that external agents use to publish a daily digest.

### Tests for Phase 4 ⚠️

- [ ] T019 [P] [US3] Add validation tests for malformed digest payloads in `tests/unit/test_web_digest_api.py`.
- [ ] T020 [P] [US3] Add tests for deterministic same-date replacement of digest groups/items in `tests/unit/test_news_digest_repo.py`.

### Implementation for Phase 4

- [ ] T021 [US3] Add payload validation rules in `src/app/web/models.py` (required group titles, non-empty summaries, bounded lengths, valid URLs as needed).
- [ ] T022 [US3] Make digest replacement transactional in `src/app/storage/repos.py`.
- [ ] T023 [US3] Add clear API error semantics in `src/app/web/app.py` for malformed submissions and unavailable storage.

**Checkpoint**: External clients can republish a day safely and predictably.

---

## Phase 5: Visual Polish for Public and Admin Surfaces

**Purpose**: Give both surfaces a minimal but intentional visual identity.

### Tests for Phase 5 ⚠️

- [ ] T024 [P] [US4] Add HTML-shell tests for public digest page structure and admin shell structure in `tests/unit/test_web_app.py`.

### Implementation for Phase 5

- [ ] T025 [US4] Refine public digest styling in `src/app/web/digest.html` (or shared CSS) with a readable digest-first layout.
- [ ] T026 [US4] Refine admin shell styling in `src/app/web/index.html` (or renamed admin template) so it remains operational but visually distinct.
- [ ] T027 [US4] Ensure both public and admin pages are mobile-safe and avoid broken layout regressions.

**Checkpoint**: The app has a clear public-product face and a separate operator console.

---

## Final Quality Gates (mandatory before merge)

- [ ] T028 Run `make lint PYTHON=./venv1/bin/python` (repo-wide) and record result.
- [ ] T029 Run `./venv1/bin/pytest` (repo-wide) and record result.
- [ ] T030 Verify unauthenticated access rules:
  - `/` public
  - digest read APIs public
  - `/admin` protected
  - admin operational APIs protected
- [ ] T031 Verify an end-to-end publication flow:
  - fetch date-scoped links
  - submit digest
  - render same digest on public page for that date
- [ ] T032 Verify no regression in existing admin update/onboarding workflows after moving the shell to `/admin`.

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 must land first because all later digest routing depends on the storage/API contract.
- Phase 2 depends on Phase 1 read APIs.
- Phase 3 depends on Phase 2 route split decisions.
- Phase 4 depends on Phase 1 write path but can overlap with late Phase 3 once auth boundaries are clear.
- Phase 5 should come last after the structure is stable.

### Parallel Opportunities

- T001/T002/T003 can run in parallel.
- T008/T009 can run in parallel.
- T013/T014/T015 can run in parallel.
- T019/T020 can run in parallel.

## Implementation Strategy

### Recommended MVP

1. Phase 1 (storage + public APIs)
2. Phase 2 (public digest page at `/`)
3. Phase 3 (move admin shell to `/admin`)
4. Phase 4 (finalize external write contract)
5. Phase 5 (visual polish)

This sequence establishes the contract first, then safely moves routing, then adds polish.

## Notes

- OpenClaw/PocketPaw/Antigravity integration should be treated as an external client workflow, not as an in-process server dependency.
- If a future phase adds authentication for digest submission, that should be modeled as a separate spec extension rather than sneaked into this feature.
- Public digest routes should be explicitly enumerated to avoid accidental auth regressions.
