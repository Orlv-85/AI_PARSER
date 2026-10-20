# Prompt: refactor the fetch pipeline without behavior change (2026-10-20)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder. `venv1` is installed editable on the main folder: in the worktree run
checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path).

## Context

`src/app/core/pipeline.md` is the feature doc of news ingestion (intended current behavior); every
rule now names its tests (PR #61). `src/app/core/pipeline.py` carries dead code, test-only branches
and duplicated logic. Make it simpler **without changing production behavior**: same requests,
same stored rows, same counters and log events, same provider calls. Read the whole doc, the
"(c) Contradictory or dead code" list in the description of PR #54 (`gh pr view 54`), and the code
before changing anything. Verify each item of that list against the current code; it may be stale.

## In scope

1. Dead code: `publication_date_evidence` in `ingest/html.py`; `rank_score(alias_count=...)`; any
   other function or branch you prove unreachable in production (grep `src/`, `scripts/`, `tests/`
   for callers). Do not remove `Settings` fields (env compatibility) or public CLI/API/MCP names;
   for `find_duplicate`, `add_alias`, `merge_alias` remove only if nothing outside tests calls them.
2. Test seams and test-only branches: the `_DEFAULT_*` comparisons in `_fetch_source_items`, the
   branches reachable only with fakes (direct `fetch_rss_with_metadata` call, one-stage `fetch_html`
   path, fallback for source types other than rss/html), the two identical HTML conditional blocks.
   Rewrite the affected tests to drive the real path (fake transport, fake fetcher, real
   `Settings`); keep every rule of the doc covered by a test that still fails when the rule breaks.
3. Duck typing for fakes: the two-name fallbacks in `_source_repo_get_fetch_state` /
   `_source_repo_update_fetch_state`, `getattr(settings, name, default)` where the field always
   exists on `Settings`. The `isinstance(session, Session)` guards around weekly writes: remove them
   only if the tests that hit them can use a real (SQLite) session; otherwise keep and say why.
4. One builder for the bounded text sent to Jev: `bounded_evidence` (`core/admission.py`),
   `_jev_state` (`core/pipeline.py`), `JevRelevanceScorer.classify` (`core/jev.py`). The text sent
   must stay byte-for-byte the same in every mode (admission, daily enrichment, plain scoring); add
   a test that pins it per mode **before** the change. If the `was_cached` check in
   `_screen_candidate` compares a different string than the one sent (daily-enrichment mode), fix
   the comparison only if the stored decisions and provider calls stay the same; otherwise report.
5. Small duplication: the known status of each link computed twice in `_process_html_links_two_stage`.
6. Named constants for the literals found in PR #61: the replay limit `limit=50`
   (`_replay_pending_for_source`) and the Comparison confidence `0.7`; the doc names the constants.
7. Doc corrections found in PR #61 (doc only, code unchanged):
   - RSS with `fetch_conditional_rss_enabled` off: validators are not sent, but are still stored.
   - Coverage: `fetch_failure` is recorded as complete; "(coverage incomplete)" applies to
     `parser_failure`. Do not change this code (weekly work is deferred).
   - An undated item marks the source coverage incomplete (RSS and HTML); add the rule with its test
     (write the test if none exists).

Keep importable what other modules and tests use: `storage/legacy_cleanup.py` imports
`_assessment_from_cached`; an integration test imports `_screen_candidate` and `AdmissionState`
(move them only together with their importers).

## Out of scope (report, do not change)

Behavior changes from the PR #54 list: the meaning of `fetched`, the missing `source_fetch_finished`
line for a failed fetch without admission, `source_count` after a pause, the RSS known-hash check
without admission. Weekly v2 code: no keep-or-delete decision now. No new features, no settings
default changes.

## Doc

`pipeline.md` must match the code in the same PR (CI checks it): Behavior and Code map for removed
paths and functions, Tests lines for renamed or rewritten tests, the new constants. Edit the doc
first where a rule changes wording.

## Work and checks

- One PR, one commit per in-scope item (or group of small ones), so each can be reviewed alone.
- Before the refactor run the full suite and keep the pass count; after it the count of tests that
  check doc rules must not drop (removed tests replaced by tests of the real path).
- `PYTHONPATH=src .../venv1/bin/python scripts/check_code_docs.py`, and after the commits
  `--diff origin/master --strict`; full gate before the push: `make lint PYTHON=...`, full `pytest`.

## Output

- Do not merge. In your reply: the PR link; per commit what changed and why it keeps behavior;
  lines removed / added in `src/`; tests rewritten or removed with their replacements; out-of-scope
  findings one line each (file:line); open questions one line each (how settled, or a yes/no
  question for the owner with a recommendation, only if it changes what readers see or what is
  paid); exact checks run with pass counts.
- Save any prompt you write for another session to a file per `AGENTS.md`.
