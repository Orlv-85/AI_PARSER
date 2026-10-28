# Prompt: 017 release R6, the month view (T050) (2026-10-28)

You are the **implementer** (background agent, Sonnet) for the 017 coordinator. You did not write the
plan; follow it. One PR, do not merge, do not tag. Production is read-only for you; no paid
provider calls (tests use `httpx.MockTransport`).

State: weeks are live (R2-R5, v0.1.134-137): numbers, `/weekly`, nightly step, weekly brief (flag on
in prod), legacy weekly retired. The brief code (R4) is already generic over the kind with month
values (packet 24,000 bytes, 5-8 sentences, $0.08 cap) and is never attempted without a month row.
Month numbers do not exist: `--kind month` answers `not_built`; month risers are `not_built`.
Owner (Q4 yes): month view as the last release; the first month shown is November 2026, on
2026-12-01. Both period flags are on in prod, so after deploy the nightly step will compute months
and brief them without further switches: get the guards right.

## Read first

`AGENTS.md`; `specs/017-weekly-monthly-signals/plan.md` ("Definitions", "Computation" month rows,
"Status and coverage rules" month column, "Decided": no October month view, "Web"); `tasks.md`
Phase 6 (T050); `src/app/core/periodic/signals_period.md` (all of it: it is the current behavior);
`period_model.py`, `period_compute.py`, `period_run.py`, `period_brief_run.py`,
`src/app/core/daily/signals_trend.py`, `storage/period_signals.py`, `web/period_view.py`,
`web/routes/period.py`, `web/routes/pages.py`, `src/app/web/pages.md`, and their tests.

## Scope: T050 exactly

- Doc first: month rules in `signals_period.md` (bounds, first month, status, month risers and
  coolers, event mix, page, nightly behavior, brief on month rows), each with tests.
- First computable month: the first full calendar month inside the comparable range (November 2026;
  October is partial and never computed, like weeks before 2026-10-12). Only completed months; the
  nightly default computes the latest completed month (cheap and idempotent every night, like weeks,
  so a failed 1st heals the next night) in addition to the latest week.
- Month risers/coolers: `trend_delta` on month totals against the previous month, with its own
  minimums (`month_*` in `PeriodThresholds`; scale the daily/weekly minimums sensibly, record the
  values as "decided 2026-10-28 (agent)"), shown only when the previous month is usable; event-type
  mix with delta; breadth suppression; status thresholds from the plan month column
  (`min_complete_days` 24, `min_items` 400, `quiet_items` 600). Bump `PERIOD_METHODOLOGY_VERSION`
  only if week payloads change (they should not; prove week payload hashes unchanged on the fixture
  week).
- CLI `--kind month` (`--period` any day of a completed month, `--backfill N`, `--recompute-all`);
  month brief through the existing R4 path on month rows (`ready` or `building_history`, not quiet).
- Web: `GET /monthly` (latest month) and `?month=YYYY-MM` (or `YYYY-MM-DD` normalized to the 1st;
  your call, record it), same states as `/weekly` (unavailable, partial, building_history, ready,
  corrupt row 200), picker; "Monthly" nav link only when a month row exists (on `/` and on
  `/weekly`; `/monthly` links back to `/weekly`); API `kind=month` and index work. Auth public
  list, route table, package data.
- Docs: `web/pages.md`, `docs/period-signals.md` (month commands, first month on 2026-12-01),
  `tasks.md` T050 ticked.
- Tests: 28/29/30/31-day months, year change (December -> January), October never computed, no
  comparison without a usable previous month (November is `building_history`), month risers rule,
  nightly default picks latest completed month and does nothing before 2026-12-01, month brief
  attempted only on a month row, page/API states, nav link hidden without month rows.

## Rules

- Do not change week behavior, daily behavior, digest, fetch, deploy workflows, compose, settings
  defaults. Money: caps stay as coded; any change goes to the owner as yes/no.
- Unclear vs. code: decide, write "decided 2026-10-28 (agent): <reason>" in the doc, list it.
- Keep code ASCII; match the style of the period code.

## Checks (from the worktree)

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b feat/017-r6-month ../AI_PARSER-wt-017r6 origin/master
cd ../AI_PARSER-wt-017r6
PYTHONPATH=src make lint PYTHON=../AI_PARSER/venv1/bin/python
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1
../AI_PARSER/venv1/bin/python scripts/check_code_docs.py --diff origin/master --strict
bash -n scripts/*.sh
```

Use `PYTHONPATH=src`. If you touch a file covered by another code doc (e.g.
`scripts/run_daily_digest_job.sh` by `core/daily/enrichment.md`), update that doc rather than
using `Docs-Skip`. No git writes in the main folder.

## Commit and PR

Commit `feat(017): R6, month view, month risers and /monthly` ending with
`Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; add this prompt file at its path under
`specs/017-weekly-monthly-signals/records/`; push; `gh pr create --base master` with: month rules
as coded, month thresholds, week-payload-unchanged proof, what happens on prod after deploy (before
and on 2026-12-01, incl. the month brief cost), decided items, checks. Body ends with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Wait for CI
(`gh pr checks <N> --watch --interval 30`); fix real failures; do not call a CI failure "local only"
without proof.

## Report (final answer)

PR URL and SHA; CI result; files with line counts; month thresholds; prod behavior before and on
2026-12-01; decided items; full gate last line; anything for the owner.
