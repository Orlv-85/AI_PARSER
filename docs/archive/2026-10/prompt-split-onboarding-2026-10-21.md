# Prompt: split `core/sources/onboarding.py` following its feature doc (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder. `venv1` is installed editable on the main folder: in the worktree run
checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path).

## Context

Step 2 of `docs/plan-split-overloaded-modules-2026-10-21.md`. The feature doc
`src/app/core/sources/onboarding.md` (PR #75, reviewed; review record
`docs/archive/2026-10/review-onboarding-doc-2026-10-21.md`) is the intended behavior. Its Code map
has the reviewed split table ("Planned split of `core/sources/onboarding.py`") and the
patch-target table. Follow them. Move code only: no behavior change.

## Do

1. Split `core/sources/onboarding.py` (~1025 lines) into `core/sources/candidates.py` (no DB, no
   network), `core/sources/validation.py`, and `core/sources/onboarding.py` (DB actions, import,
   review, YAML export), exactly as the doc's table says. Dataclasses go where no import cycle
   arises; say where. Code verbatim; `git mv` for the part that keeps history is optional, say
   which.
2. Move `SourceOnboardingService` from `web/service.py` to `web/source_onboarding.py` (next to
   `web/source_intake.py`; it returns `web/models.py` responses, so it stays in the web layer).
   `UpdateRunService` stays in `web/service.py`.
3. Delete the dead code the review confirmed (no caller outside tests): `classify_candidate_batch`,
   `write_approved_sources_yaml_snapshot`, `SourceImportBatchRepo.create_import_batch`,
   `SourceCandidateRepo.update_candidate`, `insert_normalized_draft_candidates`, with tests that only
   test them. Re-check each with grep over `src/`, `scripts/`, `tests/` first. Separate commit.
4. Imports in `src/`, `scripts/`, `tests/`; no shims at old paths. Re-point every patch target and
   quoted name listed in the doc's patch-target table (and any the doc missed: grep
   `monkeypatch.setattr`, quoted `"app.core.sources.onboarding.`, `"app.web.service.`, and
   `hasattr(source_onboarding, ...)`). A patch must hit the module where the code looks the name
   up; a patch with `raising=False` that would now miss must fail loudly instead.
5. Doc: `onboarding.md` Code map shows the final modules (the "Planned split" table becomes the
   module table), `covers:` includes the new files (`web/source_onboarding.py` too), the main
   module docstring still names the doc. Remove the dead names from the doc. Keep the two
   "code differs" rules as they are (duplicate link at `_mark_duplicate_candidate`, HTML validation
   at `_extract_links_with_ingest`): they are behavior fixes for a separate PR; update their
   file:line. Mark step 2 done in the plan file (one line).

## Do not

- Fix the "code differs" bugs, the `summarize_batch` dead status branch, or HTML validation.
- Touch weekly v2 files beyond imports, deploy files, or `sources.yaml`.

## Checks

- First, before any move: run the full suite on `origin/master` and keep the pass count.
- Full gate: `make lint PYTHON=...`, full `pytest` (same count minus removed dead-code tests; list
  them), `scripts/check_code_docs.py` and `--diff origin/master --strict`.
- Smoke: `ai-news --help`, the web app factory, the route-table pin test
  (`tests/unit/test_web_route_table.py`), `scripts/sources_onboarding_helper.py --help`.
- Package build like Docker: `pip wheel --no-deps`; the new modules are in the wheel.

## Output

- One PR, do not merge. In your reply: the PR link; module sizes; where the dataclasses went;
  dead code removed (lines) and tests removed; the re-pointed patch targets; exact checks with pass
  counts; open questions one line each (how settled, or a yes/no question for the owner with a
  recommendation, only if it changes what readers see or what is paid).
- Save any prompt you write for another session to a file per `AGENTS.md`.
