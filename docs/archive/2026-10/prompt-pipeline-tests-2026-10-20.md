# Prompt: tests for the untested rules of the fetch pipeline (2026-10-20)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder. `venv1` is installed editable on the main folder: in the worktree run
checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path to your worktree).

## Context

`src/app/core/pipeline.md` is the feature doc of news ingestion: the intended current behavior.
Each rule names the tests that check it; some rules say "no test" or "Tests: none". A refactor of
`src/app/core/pipeline.py` comes next and must be guarded by tests first. Your task is **tests
only**: no change to `src/` code. Read the doc fully, including "Tests" at the end (test files,
fakes, `_DEFAULT_FETCH_HTML` and siblings).

## The 14 rules without a test

Behavior:
1. `html_heavy` profile fetches the HTML group before the RSS group.
2. `fetch_interval_minutes` does not skip a source: every enabled source is fetched on every run.
3. RSS conditional fetch with `fetch_conditional_rss_enabled` off: no validators sent or stored.
4. A skipped RSS entry or a malformed feed marks the source coverage incomplete (weekly).
5. The `html_max_links_per_source` cap marks coverage incomplete.
6. A failed or unparsable HTML article page marks coverage incomplete.
7. Day-precision date evidence without a time sets `publication_day`, not `published_at`.
8. No similarity dedup and no aliases: two URLs of one story become two articles.
9. A duplicate in per-row mode (batch upsert off) updates scores and category; title, URL, text and
   dates stay.
10. Daily enrichment rubric: a confident Comparison answer sets `material_type`.
11. Pending replay is bounded by the `list_pending` limit.
12. RSS records known items as weekly observations too (before the known-hash check).
13. Coverage attempt outcomes `fetch_failure`, `persist_failure`, `parser_failure`.

Invariants:
14. An error outside the source loop (sources file, schema) aborts the run without a commit.

## Method

- Read the code of each rule before writing its test; test the behavior the doc states, through
  the most public entry point that is practical (`run_fetch_cycle` or the named function), with the
  existing fakes and fixtures. Put each test in the test file that already covers that area (list in
  the doc's "Tests" section); reuse helpers, do not add new frameworks or dependencies.
- No network and no provider calls (`httpx.MockTransport`, fake fetchers, fake Jev).
- A test must fail if the rule is broken: briefly check that (break the code locally, see it fail,
  revert). Do not commit that change.
- If the code does not behave as the doc says: do not change the code and do not commit a failing
  or `xfail` test. Leave the rule as "no test" in the doc and report the mismatch (rule, what the
  code does, file:line).
- If a rule cannot be tested in reasonable effort, leave "no test" and say why in the report.

## Doc edit

In `src/app/core/pipeline.md` replace each "no test" / "Tests: none" you covered with the new test
names (same style as the other Tests lines). Edit nothing else in the doc.

## Checks

- `PYTHONPATH=src .../venv1/bin/python scripts/check_code_docs.py`, and after the commit
  `--diff origin/master --strict`.
- `.../venv1/bin/python -m ruff check src tests`, then the full gate
  (`make lint PYTHON=...`, full `pytest`) before the push: this PR changes tests.

## Output

- One PR: new tests plus the Tests lines of `pipeline.md`. No `src/` code change. Do not merge.
- In your reply: the PR link; a table "rule | test name | file" (or "not covered: reason"); the
  doc/code mismatches found, one line each with file:line; the exact checks run and their result.
- Save any prompt you write for another session to a file per `AGENTS.md`.
