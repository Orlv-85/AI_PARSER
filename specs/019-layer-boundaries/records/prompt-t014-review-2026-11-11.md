# Review prompt: spec 019 T014 (use cases open the payment journal), PR 226

You review PR 226 of the repo in the current directory (a checkout of branch
`refactor/019-t014-provider-journal`, base `origin/master`). Read-only: do not edit, commit, push,
switch branches or use the network. Do not spawn a sub-agent. Do not run the full test suite (CI
ran it: green); run only the feature tests named below, with
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= -p no:cacheprovider <files>`
(and `PYTHONDONTWRITEBYTECODE=1`). Feature tests: `tests/unit/test_jev.py`,
`tests/unit/test_world_change.py`, `tests/unit/test_world_screen.py`,
`tests/unit/test_layer_imports.py`, `tests/unit/test_semantic_admission_pipeline.py`,
`tests/unit/test_provider_journal.py`, `tests/unit/test_bulletin_daily.py`.

This is a money path: the code opens the payment journal of paid Jev calls (caps, retries, usage
log). A wrong cap, a journal that is not closed, a lost stop error or a journal opened where there
was none before costs money. Review it as a money change.

## Context

Read `specs/019-layer-boundaries/tasks.md` (T014), the section "Layers" of `src/app/README.md`,
`src/app/storage/provider_journal.md` (Behavior), and `git diff origin/master...HEAD`.

The PR claims: no behavior change.

- `PilotStopped`, `TransportAttemptsExhausted` move from `src/app/storage/provider_journal.py` to
  `src/app/core/provider_errors.py`; storage imports them from there, so old import paths give the
  same class objects.
- `jev_relevance_scorer` moves from `src/app/core/jev.py` to
  `src/app/usecases/ingestion/pipeline/scorer.py`, and `open_assessor` from
  `src/app/core/bulletin/world_change.py` to `src/app/usecases/bulletin/assessor.py`; bodies are the
  same except `import_module("app.storage.provider_journal")` / `import_module("app.core.provider_costs")`
  became normal imports.
- `JevRelevanceScorer.classify` and `WorldChangeAssessor.ask` catch the stop errors from
  `core/provider_errors.py` instead of loading them by name.
- New pin tests: `test_daily_scorer_opens_capped_admission_journal`,
  `test_scorer_without_daily_enrichment_has_no_journal` (`tests/unit/test_jev.py`),
  `test_open_assessor_logs_journal_usage_on_close` (`tests/unit/test_world_change.py`).

## What to check

1. Same behavior. Compare the old bodies (`git show origin/master:src/app/core/jev.py`,
   `git show origin/master:src/app/core/bulletin/world_change.py`) with the new modules line by
   line: caps, journal path and file name, identity dict, review reason, retry delays, secret
   handling, client timeout and headers, order (key check before mkdir and journal, usage log before
   close, close in `finally`), the `except` clauses and their order in `classify` and `ask`. Report
   any difference.
2. Stop errors: is every place that raises or catches `PilotStopped` / `TransportAttemptsExhausted`
   (src and tests) still using one class object? Look for a second definition, a stale copy, or an
   `except` that now names a different class.
3. Import cycles and import time: `storage/provider_journal.py` imports
   `core/daily/provider_requests.py`, which imports `core/jev.py`. The old code used `import_module`
   inside functions, maybe to avoid a cycle. Check that every entry point still imports cleanly in a
   fresh interpreter: `app.cli.main`, `app.web.app`, `app.usecases.ingestion.pipeline`,
   `app.usecases.world_screen`, `app.usecases.bulletin.daily`, `app.core.jev`,
   `app.core.bulletin.world_change`, `app.storage.provider_journal` (each with
   `PYTHONPATH=src .../.venv/bin/python -c "import <module>"`).
4. Monkeypatch targets and tests that pass for the wrong reason: tests that patch
   `app.core.jev.*` or `app.core.bulletin.world_change.*` names that no longer exist or are no
   longer read there; `monkeypatch.setattr(..., raising=False)`; tests that patch `cli_main.open_assessor`
   or `cycle.jev_relevance_scorer` (do they still hit the name the code reads?).
5. The new pin tests: would they catch a wrong cap, a wrong path, a missing close, a missing usage
   log, a journal opened without daily enrichment? Name a mutation of the openers that survives.
6. `tests/unit/test_layer_imports.py`: does `test_core_imports_no_lower_or_upper_layer` really show
   that `src/app/core` imports nothing from `app.storage` in any form?
7. Docs: `src/app/README.md` ("Layers", package rows), `world_change.md`, `pipeline.md`,
   `provider_journal.md`, `tasks.md`: wrong statements about where code lives or what it does.
8. Stale references to `app.core.jev.jev_relevance_scorer` or
   `app.core.bulletin.world_change.open_assessor` anywhere that is not history (`specs/`,
   `docs/archive/`, `docs/work/` are history): scripts, workflows, Dockerfile, `pyproject.toml`,
   strings.

## Report

Reply with a list of findings, each: severity (blocker / should fix / note), file and line, what is
wrong, what you checked to be sure. Say plainly what you did not check. No praise, no summary of the
PR. If you find nothing in a point, say "nothing found" for that point.
