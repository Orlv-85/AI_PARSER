# Prompt: 017 release R2, PR 2 of 2: storage, CLI, nightly step, API (T013-T015) (2026-10-28)

You are the **implementer** (background agent, Sonnet) for the 017 coordinator. You did not write the
plan; follow it. One PR, do not merge, do not tag. Production is read-only for you.

PR 1 of R2 (#132, T010-T012) is merged: `src/app/core/periodic/` (`period_model.py`,
`period_compute.py`, `signals_period.py`, code doc `signals_period.md`) and
`src/app/core/daily/signals_trend.py`. This PR makes it run and readable. With the flag off (default)
nothing changes for readers or for the nightly job.

## Read first

`AGENTS.md`; `specs/017-weekly-monthly-signals/plan.md` ("Storage", "Versions", "Run and backfill",
"Web", "Rollout"); `tasks.md` Phase 2 (T013-T015); `src/app/core/periodic/signals_period.md` (its
"Next PR" paragraph and the R2a decisions: previous period usable when `ready` or
`building_history`; the helper path needs 14 days of inputs); how 006 does the same things: the
daily signals repo in `src/app/storage/` (`git grep -n "class .*Signal.*Repo" src/app/storage`),
its migration (`git grep -ln daily_signal_reports src/app/storage/migrations`), the
`daily-signals` CLI command in `src/app/cli/main.py`, its step in `scripts/run_daily_digest_job.sh`,
its API route and models in `src/app/web/`; `src/app/core/daily/signals.md` (Invariants: "writes
only its own tables"); `docs/troubleshooting.md`.

## Scope: T013, T014, T015 exactly

Edit `signals_period.md` first (Behavior for storage, run, flag, API state; Code map; Tests), then
code; doc matches code at the end. Extend `covers:` with the globs this PR ships
(`src/app/storage/period_signals*.py`, `src/app/storage/migrations/versions/*period_signal*.py`,
`src/app/web/routes/period.py`).

**T013.** Models `PeriodSignalReport`, `PeriodSignalBrief` (`storage/models_sql.py`, columns from the
plan table, unique on kind + start, no FK to `articles`); Alembic migration with `down_revision` =
current head (`alembic heads` must show one head), skipping objects `create_all()` already made, the
same way as the 006/007 migrations; `storage/period_signals.py` `PeriodSignalRepo`: load a
`PeriodInput` for (kind, start) including the 7 days before the period for the helper path and the
stored previous period row (`PreviousPeriod`), upsert only when `payload_hash` changed, read latest
ready/any, index of stored periods. The brief table is created now (empty) so R4 needs no migration.
Tests: migration upgrade/downgrade on SQLite; repo round trip; upsert idempotent (second run writes
nothing); "a period run writes only `period_signal_*` tables" (like the 006 invariant test).

**T014.** CLI `ai-news period-signals [--kind week|month] [--period YYYY-MM-DD] [--backfill N]
[--recompute-all]` (no `--with-brief`/`--max-usd` yet: R4), setting `AINEWS_PERIOD_SIGNALS_ENABLED`
(default off; off: the command says so and exits 0 without writing, like `daily-signals`). Default
run: the latest completed week; on the 1st also the latest completed month only when month
computation exists (it does not until R6: month kind is rejected or reported `not_built`, your call,
record it). Never computes a week before the week of `COMPARABLE_FROM` or an uncompleted week.
JSON run report like `daily-signals`. Step at the end of `scripts/run_daily_digest_job.sh` after
daily signals with the same guards (time budget, failure never changes the job result); `bash -n
scripts/*.sh`. Operator doc `docs/period-signals.md` (enable, backfill 3, recompute, rollback),
registered in `docs/README.md`; mention the flag in `docs/configuration.md`. Do not add the flag to
deploy workflows, compose or `.env.prod.example` (plan: as for 006, the operator sets it).

**T015.** `GET /api/news/period-signals?kind=week&start=YYYY-MM-DD` (default latest) and
`GET /api/news/period-signals/index` in `web/routes/period.py`, new response models in
`web/models.py` (no change to existing models); stored data only; missing row or corrupt payload
gives 200 with an `unavailable` state, never 500; `brief` is null. Register the router; update the
route table test. Tests: ready, partial, unavailable, corrupt row, index order, no provider import
on the request path.

## Rules

- Do not touch the daily signals behavior, digest, fetch, auth, ports, retention, deploy workflows,
  compose. `scripts/run_daily_digest_job.sh` is production-sensitive: show its full hunk in the PR body.
- If the plan is unclear against the code, decide, write "decided 2026-10-28 (agent): <reason>" in
  the doc, list it in the report. Product or money questions: stop, report as yes/no with a
  recommendation.
- Keep code ASCII; match the style of the 006 counterparts.

## Checks (from the worktree)

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b feat/017-r2b-period-storage ../AI_PARSER-wt-017r2b origin/master
cd ../AI_PARSER-wt-017r2b
make lint PYTHON=../AI_PARSER/venv1/bin/python
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1
../AI_PARSER/venv1/bin/python scripts/check_code_docs.py
bash -n scripts/*.sh
```

`pytest -q` prints no summary line here. If a PostgreSQL integration test exists for the 006 tables,
add the period tables to it the same way. No git writes in the main folder.

## Commit and PR

Commit `feat(017): R2b, period signals storage, CLI, nightly step and API` ending with
`Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; add this prompt file at its path under
`specs/017-weekly-monthly-signals/records/`; push; `gh pr create --base master` with: what each task
added, migration revision and head, the `run_daily_digest_job.sh` hunk, behavior with the flag off,
"decided (agent)" items, checks. Body ends with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Wait for CI
(`gh pr checks <N> --watch --interval 30`); fix real failures (`gh run view <id> --log-failed`); do
not call a CI failure "local only" without proof.

## Report (final answer)

PR URL and SHA; CI result; new/changed files with line counts; migration revision; flag-off proof
(which test); "decided (agent)" items; full gate last line; operator steps after deploy
(enable flag, `--backfill 3`); anything unclear.
