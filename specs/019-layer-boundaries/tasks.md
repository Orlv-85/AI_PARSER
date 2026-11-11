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

- [x] T009 `ArticleRepo.prune_older_than` takes a required `archive` function and calls it before
  the deletes; the use case `prune_articles` (`usecases/archive/capture.py`) passes
  `archive_articles`. Same transaction, same order; local import removed; `storage/` imports no
  `usecases/`.
- [x] T010 `storage/daily_signals.py`: `reconcile`, `digest_title`, `digest_summary` calls move to
  the use case. Done: `recompute_reports` (with `RecomputeResult`, `RECOMPUTE_DAYS`,
  `SETTLED_DAYS`) moves unchanged to `usecases/daily/signals_recompute.py`; the selector conflict
  check of `add_override` moves to `usecases/daily/signals.py` (`add_override`), the repository
  keeps `insert_override`; `observations` and `digest_items` return the stored text and
  `digest_text` (use case) applies `digest_title` / `digest_summary` for the daily recompute and
  the period run. The brief packets already cleaned item summaries (`ArticleRefs.ref`), so
  `digest_items` needs no cleaning. `_keep` becomes public `stored_days_to_keep`. A new test pins
  the digest title in the report; the storage-side check has no listed files.
- [x] T011 `storage/period_signals.py`: `reconcile` call moves to `usecases/periodic/period_run.py`
  (`context` takes the reconciliation, `load_input` needs a context). The storage-side check of
  calculating functions starts here with two listed files (T010, T012); a new test pins that the
  period run applies overrides (nothing did before).
- [x] T012 `storage/bulletin_input.py` is a use case as a whole (it opens no session but runs
  queries over five tables, calls `digest_title` and `cluster_key` and assembles `DayInput`): the
  module moves to `usecases/bulletin/day_input.py` unchanged. `cluster_key` stays in
  `storage/world.py`: the rule bans only `core` calculations in storage, and `world.py` calls it
  itself; decided 2026-11-11 (agent).

## Phase 5: Close (US3)

- [ ] T013 Test: `storage/` imports from `core/` only names on an allowed list of types and
  constants; lasting intent stays in `src/app/README.md`; spec status set to shipped.

## Phase 6: Found by the review of PR 221 (records/review-step2-2026-11-10.md)

- [x] T014 `core/jev.py` and `core/bulletin/world_change.py` load `app.storage.provider_journal` by
  name (`import_module`) to build the payment journal and to name its errors. The use case builds
  the journal and passes it in; the errors the rule code must catch move to `core/`. Money path:
  tests pin the journal calls first; reviewed as a money change.
  Done: `PilotStopped`, `TransportAttemptsExhausted` move to `core/provider_errors.py` (storage
  imports them from there, so old import paths still work); the openers move to use cases:
  `jev_relevance_scorer` to `usecases/ingestion/pipeline/scorer.py`, `open_assessor` to
  `usecases/bulletin/assessor.py`. New pin tests (journal path, identity, caps, retry, usage log,
  close) were written and seen passing on the old code first. `core/` imports no `storage/`.
  `core/jev.py` no longer imports `app.config` (one less file for T015).
- [x] T015 `ingest/` and `config/` have no place in the rule. `core/` imports `app.ingest` (3 files)
  and `app.config` (1 file since T014: `core/sources/review.py`), `ingest/` imports `core/` back (3 files), and `config/sources.py`
  loads `app.storage.models_sql` by name. Decide the place of each package, then extend the test.
  Done, decided 2026-11-11 (agent): the chain is `usecases -> storage -> ingest -> core`; `ingest`
  is the network and parsing adapter and imports no `storage`, `usecases`, `web`, `cli`; `storage`
  may use it (the page cache `article_evidence_cache.py` parses pages through it; moving the cache
  to `ingest` would make `ingest` import storage's private file writes). `config` and
  `observability` are leaves: they import no other `app` package. Moves, code unchanged:
  `ingest/page_filter.py` -> `core/ingestion/page_filter.py` (pure rules, used by
  `core/ingestion/reject_policy.py`), the bot identity from `ingest/fetcher.py` ->
  `core/bot_identity.py` (used by `core/world/gdelt.py`, `core/sources/review.py`),
  `bootstrap_sources_into_db` from `config/sources.py` -> `usecases/sources/bootstrap.py`.
  `core/sources/review.py` keeps importing `Settings` from the leaf `config`.
