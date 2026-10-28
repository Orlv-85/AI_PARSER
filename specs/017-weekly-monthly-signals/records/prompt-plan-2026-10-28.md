# Prompt: plan spec 017, weekly and monthly signals (Phase A, planning only) (2026-10-28)

You are the **planner** (background agent, Sonnet) for coordinator `ai-parser-ba`. Planning only: no
code in `src/` or `tests/`, no prod writes. A different agent implements later, after the
coordinator's review and the owner's answers. Output: a spec-only PR.

## Context

- Backlog B2 (`docs/backlog/backlog-todo.json`): weekly and monthly analytics on the 006 data layer
  (per-article entities and event types from Daily AI Signals). The legacy weekly block mostly shows
  "Insufficient comparable source coverage". 006 goal G5 wants the per-article data reused for
  weekly/monthly views.
- Live today: Daily AI Signals (006) and its brief (007), Rising/Cooling on `/` since 2026-10-23
  (needs two full weeks of snapshots). Code doc: `src/app/core/daily/signals.md` (read it first).
- Weekly v2 (spec 010, `core/weekly/`, `storage/weekly.py`, `weekly_*` tables, about 2350 lines) is
  **off** on prod (`AINEWS_WEEKLY_V2_ENABLED=false`); the legacy weekly job has not run since
  2026-10-05 (no cron). Its fate was deferred until weekly work starts: **now**.
- Open item moved here from F1: a failed source fetch is recorded as complete weekly coverage
  (`cycle.py` `record_attempt(outcome="fetch_failure", complete=True)`); recommended `complete=False`.
- Data: collection since 2026-07-03; 006 signals since about 2026-10-12 (check the first day with
  `article_signals` / snapshots on prod, read-only).

## Read first

`AGENTS.md` (Specs, Feature Docs Next To Code, Owner And Questions), `.specify/templates/`
(spec, plan, tasks formats), `src/app/core/daily/signals.md`, `specs/006-daily-ai-signals/spec.md`
(G5) and `plan.md`, `specs/010-weekly-ai-analytics-for-management-dashboard/` (what weekly v2 does),
`docs/weekly-analytics.md`, the weekly pages and routes (`src/app/web/weekly_analytics*.html`,
`src/app/web/routes/weekly.py`).

## Questions the plan must answer

1. **Weekly v2: keep or delete.** Facts: what it computes, what it costs per run (provider calls),
   what of it the new feature could reuse (tables, frozen runs, coverage), test and lint weight.
   Recommend one; if delete, list exactly what goes (files, tables via a migration, routes, pages,
   docs, settings, workflows) and what stays.
2. **What readers see.** Proposed weekly and monthly views built from 006 data: e.g. top entities by
   mentions and sources, new entities of the week, risers/coolers week over week, event-type mix,
   a short weekly brief (like 007, paid). Where on the site (pages, URLs), how they relate to `/`.
   Keep it small for a first version; mark what is v1 vs later.
3. **Data and computation.** From which tables; deterministic parts vs paid model calls; how a week
   and a month are defined (UTC, Monday start?); minimum coverage rules; caching and versions like
   006 (frozen snapshots, version constants); backfill for past weeks.
4. **Cost.** Paid calls per week/month and USD estimate with the 006/007 prices; caps.
5. **Coverage.** The F1 item above and how coverage is judged for a week.
6. **Rollout.** Flags, deploy order, rollback, tests, code doc for the new feature (name the main
   module and its `.md`).

## Output

1. Worktree: `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b spec/017-weekly-monthly-signals ../AI_PARSER-wt-017 origin/master`. No git writes in the main folder.
2. Write `specs/017-weekly-monthly-signals/spec.md`, `plan.md`, `tasks.md` in the `.specify/templates/`
   format (English). `plan.md` has the weekly v2 decision section with evidence and a section
   "Owner questions": only product (what readers see) and money (paid calls, budgets) questions, each
   as a yes/no question with a recommendation; everything else you decide and record as
   "decided 2026-10-28 (planner): ...".
3. Copy this prompt into the same `records/` folder in the worktree
   (`cp /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/017-weekly-monthly-signals/records/prompt-plan-2026-10-28.md specs/017-weekly-monthly-signals/records/`).
4. Checks: `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests -k code_docs -p no:cacheprovider -o addopts="" | tail -1`.
5. Commit `docs(017): plan weekly and monthly signals` ending with
   `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push; `gh pr create --base master`
   (spec-only; body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`). Do not merge.

Prod: read-only (`ssh -o BatchMode=yes ai-news`, SELECT only via
`docker exec -i ai-news-db psql -U ainews -d ainews` with SQL on stdin), only to get facts (row
counts, first days, sizes).

## Report (final answer)

PR URL; weekly v2 recommendation in two lines with the main numbers; the v1 reader-facing views in
a short list; cost estimate per week/month; the owner questions (yes/no with recommendation).
