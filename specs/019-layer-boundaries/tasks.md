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

- [x] T004 Read the dependencies of each use-case file: only `digest_title` (in
  `daily/enrichment.py`) was imported by `storage/` and by a `core/` module.
- [x] T005 `digest_title` and its pattern move to `core/daily/titles.py`. Other rules inside the
  moved files stay there: decided 2026-11-10 (agent), they are split out when that code next
  changes for a real task (owner rule of 2026-11-03 for refactors).
- [x] T006 Move to `src/app/usecases/`: the 13 use-case modules, the whole `ingestion/pipeline/`
  package (its `fetch.py` and `models.py` are used only by the pipeline) and the six feature docs
  whose main module moved. Imports, monkeypatch targets, doc headers and registries updated.
- [x] T007 `tests/unit/test_layer_imports.py`: `core/` imports no `usecases/`, `cli/`, `web/`; it
  imports `storage/` only in the two files of T014. The scan also reads `import_module("...")`
  and `__import__("...")` with a literal name; relative imports are banned by a test.

## Phase 3: Storage does not import use cases (US3)

- [x] T008 Same test file: `storage/` imports `usecases/` only in `article_repo.py` (until T009).

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

## Phase 6: Found by the review of PR 221 (records/review-step2-2026-11-10.md)

- [ ] T014 `core/jev.py` and `core/bulletin/world_change.py` load `app.storage.provider_journal` by
  name (`import_module`) to build the payment journal and to name its errors. The use case builds
  the journal and passes it in; the errors the rule code must catch move to `core/`. Money path:
  tests pin the journal calls first; reviewed as a money change.
- [ ] T015 `ingest/` and `config/` have no place in the rule. `core/` imports `app.ingest` (3 files)
  and `app.config` (2 files), `ingest/` imports `core/` back (3 files), and `config/sources.py`
  loads `app.storage.models_sql` by name. Decide the place of each package, then extend the test.
