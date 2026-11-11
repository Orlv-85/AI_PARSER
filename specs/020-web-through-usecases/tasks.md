---
description: "Tasks: entry points go through use cases (020)"
---

# Tasks: Entry points go through use cases

**Input**: `specs/020-web-through-usecases/spec.md`, `plan.md`

One phase = one PR. Each PR: the rule text in `src/app/README.md` ("Layers") or the feature doc
first, then the failing test, then the code; full gate before push
(`make lint PYTHON=./.venv/bin/python`, `./.venv/bin/pytest`); UB tools on changed files.

## Phase 1: Entry-point check (US1)

- [ ] T001 Rule text in `src/app/README.md` ("Layers"): entry points import from storage only
  `models_sql`; `web/app.py` is the composition root (FR-001, FR-002).
- [ ] T002 `tests/unit/test_layer_imports.py`: a name-aware scan helper with its own tests (plan,
  step 1); `STORAGE_IN_ENTRY_POINTS` and `COMMITS_IN_WEB`, each equal to what the scan finds; a
  test that `web/app.py` imports only the allowed names.

## Phase 2: Tables once per app (US2)

- [ ] T003 `src/app/web/pages.md`, `src/app/usecases/sources/onboarding.md`: "once per app
  instance" rule with test names.
- [ ] T004 Failing tests (plan, step 2): once per initializer, retry after a 503, two concurrent
  first requests, a fresh app calls again; for both initializers.
- [ ] T005 `_once` wrapper with one per-app lock in `web/app.py`;
  `WebDeps.create_onboarding_tables`; `routes/sources.py` no longer imports `Base`.

## Phase 3: Bodies through Pydantic (US3)

- [ ] T006 `onboarding.md` and `pages.md`: bad-body answers (FR-005) with test names.
- [ ] T007 Failing tests (plan, step 3): bad bodies on the three paths, fractional ids, kept
  coercions and error order, auth-off login, OpenAPI of the three operations; adjust
  `test_auth_middleware_coverage_is_pinned`.
- [ ] T008 Three models in `web/models.py` with `mode="before"` validators; handlers read them
  inside the handler; the two `_parse_source_onboarding_*` helpers removed; the pinned tests
  listed in the plan stay green.

## Phase 4: Handlers call use cases (US1) - after the owner's go, one PR per group

- [ ] T009 Groups and order decided after phase 3 (start: source onboarding).
