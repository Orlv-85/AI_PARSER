# Prompt: 017 T041, drop the weekly v2 tables (2026-10-28)

You are the **implementer** (background agent, Sonnet) for the 017 coordinator. One PR, do not
merge, do not tag. Production is read-only for you.

State: weekly v2 code was deleted in R1 (v0.1.133); its 8 tables stay with their model classes.
The coordinator verified a restore of the latest dump (all 8 tables equal to prod):
`specs/017-weekly-monthly-signals/records/report-t041-restore-2026-10-28.md` (add it to this PR,
it is in the main folder, untracked). Owner approved the drop (Q1 yes, 2026-10-28).

## Read first

`AGENTS.md`; `plan.md` ("What goes, what stays", Stage 4; "Rollout" rollback); `tasks.md` T041;
`src/app/storage/models_sql.py` (the 8 classes); the migrations that created them
(`8b3a2d4e9f10`, `e12a640c9b32`) and the latest period migrations (how `create_all()`-made objects
are skipped); `git grep -n "Weekly\(SourceVersion\|CoverageAttempt\|InputObservation\|Decision\|TopicVersion\|Job\|Snapshot\|Publication\)\|weekly_\(source_versions\|coverage_attempts\|input_observations\|decisions\|topic_versions\|jobs\|snapshots\|publications\)" src tests scripts`.

## Scope

- Alembic migration, `down_revision` = current head (`alembic heads`: one head after it):
  upgrade drops `weekly_source_versions`, `weekly_coverage_attempts`, `weekly_input_observations`,
  `weekly_decisions`, `weekly_topic_versions`, `weekly_jobs`, `weekly_snapshots`,
  `weekly_publications` with `IF EXISTS` in FK-safe order (works on PostgreSQL and SQLite);
  downgrade recreates them empty with the same columns, indexes and constraints as the original
  migrations (copy, do not import from the models you delete).
- Delete their model classes from `models_sql.py`; keep `weekly_analytics_reports` /
  `weekly_analytics_items` and `WeeklyAnalyticsRepo` (legacy API). Fix every remaining reference
  (tests, cleanup/retention lists, db maintenance scripts, docs table lists).
- Tests: migration upgrade drops the 8 tables and downgrade recreates them (SQLite); `create_all()`
  on a fresh DB creates none of them; the full chain upgrade from base to head works on SQLite.
  If a PostgreSQL integration test exists for migrations, extend it.
- Docs: the code doc that covers `models_sql.py`/migrations if any (check `covers:` globs with
  `git grep -n "models_sql\|migrations" -- '*.md'`), `signals_period.md` Decisions one line
  (v2 tables dropped, restore report path), `tasks.md` T041 ticked, `docs/deploy.md` or
  `docs/troubleshooting.md` only if they list these tables.

## Rules

- Do not touch other tables, retention, deploy workflows, compose.
- Unclear: decide, write "decided 2026-10-28 (agent): <reason>", list it.

## Checks (from the worktree)

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b feat/017-t041-drop-v2-tables ../AI_PARSER-wt-017t041 origin/master
cd ../AI_PARSER-wt-017t041
PYTHONPATH=src make lint PYTHON=../AI_PARSER/venv1/bin/python
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1
../AI_PARSER/venv1/bin/python scripts/check_code_docs.py --diff origin/master --strict
PYTHONPATH=src ../AI_PARSER/venv1/bin/alembic heads
```

No git writes in the main folder.

## Commit and PR

Commit `feat(017): T041, drop the weekly v2 tables` ending with
`Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; add this prompt and the restore report
under `specs/017-weekly-monthly-signals/records/`; push; `gh pr create --base master` with: the
migration (revision, down_revision, SQL of upgrade), deleted classes with grep proof, rollback,
checks. Body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Wait for
CI (`gh pr checks <N> --watch --interval 30`); fix real failures.

## Report (final answer)

PR URL and SHA; CI result; migration revision; deleted classes; full gate last line; anything unclear.
