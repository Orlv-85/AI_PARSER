# Prompt: behavior-neutral cleanup - "pilot" module names, finished re-enrichment scripts, dead onboarding branch (2026-10-24)

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. One PR, **no behavior change**: no change to
CLI flags, API responses, stored data, version strings, prompts or provider requests. Report to the
coordinator (the session that started you) at the end. Do not ask the owner anything.

## Read first

`AGENTS.md`; `docs/plan-storage-layout-2026-10-21.md` (sections on `reenrich_pilot_journal.py`,
re-enrichment, weekly `code_hashes`); `src/app/core/daily/enrichment.md`;
`src/app/core/sources/onboarding.md` ("Lists and summaries").

## Steps

1. Worktree: `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch` then
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add ../AI_PARSER-wt-cleanup-pilot -b refactor/cleanup-pilot-names-20261024 origin/master`.
   Work only there. Checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/<tool>` from the worktree root.

2. **Rename modules (move-only, `git mv`)**:
   - `src/app/storage/reenrich_pilot_journal.py` -> `src/app/storage/provider_journal.py`
   - `src/app/core/daily/reenrich_pilot.py` -> `src/app/core/daily/provider_requests.py`
   - Keep every name inside them (classes such as `PilotJournal`, functions, constants) and every
     string value (`PILOT_VERSION = "reenrich-pilot-1"` etc. are stored in data: unchanged).
   - Re-point all imports and monkeypatch targets in `src/`, `scripts/`, `tests/`
     (`git grep -n "reenrich_pilot"`). Rename `tests/unit/test_reenrich_pilot.py` to
     `tests/unit/test_provider_requests.py` only if it tests the core module (not the script).
   - `src/app/core/weekly/frozen.py` `code_hashes()` names the journal path: update the path.
     Weekly is off in production; existing frozen weekly runs refusing to resume is accepted
     (decided in the plan doc). Say it in the PR body.
   - Code docs (`enrichment.md`, `pipeline.md`, `signals.md`, any `covers:` globs), `src/app/README.md`,
     `docs/plan-storage-layout-2026-10-21.md` table: new paths. Do not edit files under `docs/archive/`
     or `specs/`.

3. **Delete the finished re-enrichment tools** (re-enrichment finished 2026-10-11, record in
   `docs/archive/2026-10/reenrich-production-results-2026-10-11.md`):
   - `scripts/reenrich_articles.py`, `scripts/reenrich_pilot.py` and tests that only test these
     scripts (e.g. `tests/unit/test_reenrich_script.py`; check each test file).
   - `src/app/storage/article_snapshot.py` and `tests/unit/test_article_snapshot.py` **only if**
     nothing else in `src/` or `scripts/` imports it after the deletion; else keep.
   - Any code in `src/` used only by these scripts: list it; delete only what is provably dead
     (`git grep` shows no other user), otherwise keep and list it in the report.
   - `docs/article-reenrichment.md`: `git mv` to `docs/archive/2026-10/`; fix links to it
     (`docs/README.md`, `README.md`).

4. **Onboarding dead branch**: in `src/app/storage/source_candidate_repo.py` `summarize_batch`, the
   `validated` status branch never matches (no candidate has status `validated`; see
   `onboarding.md` "Lists and summaries"). Remove that branch; counts stay identical. Update the
   doc sentence about it. Do NOT change HTML validation or URL normalization (those are behavior
   changes, they stay in the backlog).

5. Checks: `git grep -n "reenrich_pilot\|reenrich_articles"` in `src scripts tests` returns nothing
   (except stored version strings like `"reenrich-pilot-1"`); full gate:
   `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
   For each renamed module confirm the content is unchanged except imports:
   `git diff -M origin/master --stat` shows renames with high similarity; paste it in the report.

6. Commit `refactor: rename pilot modules, remove finished re-enrichment tools` with the line
   `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; push;
   `gh pr create --base master --title "refactor: rename pilot modules, remove finished re-enrichment tools" --body "<what moved, what was deleted and why it was dead, weekly code_hashes note, checks>"`.
   Do not merge.

## Report

PR link and head SHA; `git diff -M --stat`; deleted files and the evidence they were dead; kept
code that only the scripts used; gate results (counts); anything you were unsure about.
