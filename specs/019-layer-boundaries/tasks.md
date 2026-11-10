---
description: "Tasks: layer boundaries (019)"
---

# Tasks: Layer boundaries

**Input**: `specs/019-layer-boundaries/spec.md`, `plan.md`

One phase = one PR unless said otherwise. Each PR: the rule text in `src/app/README.md` ("Layers")
or the feature doc first, then the failing test, then the code; full gate before push
(`make lint PYTHON=./.venv/bin/python`, `./.venv/bin/pytest`); UB tools on changed files.

## Phase 1: Canonical JSON to core (US1, US3)

- [x] T001 Rule text: section "Layers" in `src/app/README.md`.
- [x] T002 Failing test `tests/unit/test_layer_imports.py` (list of use cases still in `core/`).
- [x] T003 `src/app/core/canonical_json.py`; `storage/journal_files.py` keeps private writes; all
  imports in `src/` and `tests/` point to the new module; pinned fingerprint test moves to
  `tests/unit/test_canonical_json.py`.

## Phase 2: Use cases out of core (US1)

- [ ] T004 Read each file of `USE_CASES_IN_CORE`; list rule/use-case splits in the PR body.
- [ ] T005 Split mixed files (rule stays in `core/`), tests first where a function moves.
- [ ] T006 Move the use cases to `src/app/usecases/`; update imports, monkeypatch targets, code doc
  headers and registries, scripts that name module paths.
- [ ] T007 `USE_CASES_IN_CORE` is deleted; the test asserts no `core/` file imports `storage/`.

## Phase 3: Storage does not import use cases (US3)

- [ ] T008 Test: no `storage/` file imports `app.usecases` (exception: `article_repo.py` until T009).

## Phase 4: Calculations out of repositories (US2) - one PR per task

- [ ] T009 `ArticleRepo.prune_older_than`: archive step moves to a use case; same transaction, same
  order; local import removed.
- [ ] T010 `storage/daily_signals.py`: `reconcile`, `digest_title`, `digest_summary` calls move to
  the use case.
- [ ] T011 `storage/period_signals.py`: `reconcile` call moves to the use case.
- [ ] T012 `storage/bulletin_input.py`: `digest_title`, `cluster_key` calls move to the use case.

## Phase 5: Close (US3)

- [ ] T013 Test: `storage/` imports from `core/` only names on an allowed list of types and
  constants; lasting intent stays in `src/app/README.md`; spec status set to shipped.
