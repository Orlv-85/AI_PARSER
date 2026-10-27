# Prompt: archive-old feed items are reopened as pending every night (2026-10-27)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. You investigate, fix with a test
and open a PR. Do not merge, do not tag. Production is read-only for you.

## Finding (coordinator, prod read-only, 2026-10-27)

- `admission_decisions`: 516 rows `provider_status='pending'`; 445 of them are `openai_news`,
  created 2026-10-12, candidate `kind='article'`, `published_at` 2015-12-11 .. 2026-06-30 (ISO,
  parseable), `attempts=17`, `updated_at` every night at ~01:00:44-46 UTC (the openai_news fetch).
- 763 rows are `settled` with `reason='stale_pending'`.
- `PENDING_REPLAY_MAX_AGE_DAYS = 30` (`src/app/core/ingestion/pipeline/models.py`), so these
  candidates are stale by the rule in `src/app/core/ingestion/pipeline.md` (Behavior: "A pending
  body candidate whose stored `published_at` is older than `PENDING_REPLAY_MAX_AGE_DAYS` is archive
  material: it is settled (`stale_pending`) ...").
- The openai_news RSS returns 1325 items every night (`source_fetch_finished`: fetched_items 1325,
  new 2, duplicates 24, skipped_known 24, early_stop_hit true, replay_items 0,
  semantic_rejected 8, semantic_unresolved 24, semantic_cache_hits 27).
- Hypothesis: `_take_fresh_pending` (`pipeline/replay.py`) settles them as stale, then the fresh
  feed processing of the same source calls `upsert_pending` (`src/app/storage/admission.py`),
  which reopens any row that is not `ok` with a decision (settled -> pending, attempts + 1).
  Confirm or refute; there may be another path.

## Questions to answer (in the report)

1. Exact path that reopens them (function chain, file:line).
2. Does any of these old items reach Jev (a paid call) on a normal night? Count from code and, if
   possible, from the log line fields above. If yes, estimate calls per night.
3. Does anything reader-visible change (stored articles, digest)? Expected: no.

## Fix rules

- Read `AGENTS.md` ("Feature Docs Next To Code", "Validation") and `src/app/core/ingestion/pipeline.md`
  first. Behavior change starts in the doc: add or adjust the rule (e.g. a fresh feed item older
  than `PENDING_REPLAY_MAX_AGE_DAYS` does not create or reopen a pending row; or a row settled as
  `stale_pending` is not reopened by `upsert_pending`), with its test names. Choose the smallest fix
  that keeps every existing rule and test; say why in Decisions (one line).
- Tests first: a test that reproduces the reopen (fails before the fix) in the style of the tests
  named in pipeline.md for stale pending (`test_stale_pending_candidate_is_settled_without_screening`
  and neighbours).
- Do not change Jev calls for fresh items within the window, admission policy versions, or
  anything readers see.

## Steps

1. `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b fix/stale-pending-reopen-20261027 ../AI_PARSER-wt-stale origin/master`. No git writes in the main folder.
2. Optional prod reads only: `ssh -o BatchMode=yes ai-news 'docker exec -i ai-news-db psql -U ainews -d ainews -At' <<'SQL' ... SQL` with `SELECT` only, and `grep` on `/opt/ai-news/logs/daily-fetch.log`. Nothing else on the server.
3. Doc, test, fix. Checks from the worktree: `make lint PYTHON=../AI_PARSER/venv1/bin/python`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest` (full; report the summary line, run without `-q`
   or add `-rA | tail`), `../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
   Do not use `until grep ...` waits on test output.
4. Commit `fix(admission): do not reopen archive-old pending candidates every night` ending with
   `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push; `gh pr create --base master`
   with the findings, the fix, checks; body ends with
   `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final answer)

PR URL and SHA; answers to the three questions; the doc rule added; tests added (names, fail before /
pass after); full gate result; whether the 445 existing rows settle on the next night after deploy
or need a one-off action (do not run one; describe it).
