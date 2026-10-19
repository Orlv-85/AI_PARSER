# Prompt: 007 Daily Signals Brief - plan, then implement (2026-10-19)

You are the implementer for feature `007-daily-signals-brief` in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, FastAPI, Typer, SQLAlchemy/Alembic;
production on PostgreSQL). It is a small iteration on the live Daily AI Signals block (006). A
coordinator session reviews your work at each checkpoint. Stop at every checkpoint.

## Work in your own worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-007-impl -b feat/007-daily-signals-brief origin/master
cd ../AI_PARSER-007-impl
```

Do not work in the main folder. Use `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1`, no `.env` in
the worktree for tests (see `docs/troubleshooting.md`).

## Read first

1. `AGENTS.md`, `docs/troubleshooting.md`
2. `.specify/specs/007-daily-signals-brief/spec.md` (contract)
3. 006 context: `.specify/specs/006-daily-ai-signals/plan.md` (Decisions 1-7, Deferred),
   `dry-run.md` sections 8-11, `docs/daily-signals.md`
4. Code: `src/app/core/daily_signals*.py`, `src/app/storage/daily_signals*.py`,
   `src/app/web/signals_view.py`, `src/app/web/models.py`, `src/app/web/digest.html`,
   `src/app/core/weekly_narrative.py` (grounded narrative pattern to reuse)
5. Live block: `https://5kzt.l.time4vps.cloud/?date=2026-10-16` and `?date=2026-10-17`;
   API `https://5kzt.l.time4vps.cloud/api/news/daily-signals?date=2026-10-16`

## Checkpoint 1 - plan (stop)

Write `.specify/specs/007-daily-signals-brief/plan.md` and `tasks.md` (format as in 006, much
shorter): brief prompt and JSON schema, validation, storage and versioning, one-liner rule, noise rules
with exact constants, quiet-day rendering, API fields, UI wireframe (ASCII), job integration, tests,
cost. Answer the spec's Open Questions with a recommendation.

Include a **dry-run**: on a local scratch copy with the production snapshots of 2026-10-12..18
(import via the public API `GET /api/news/daily-signals?date=` and `GET /api/news/digests?date=`;
read-only), generate briefs for those 7 days with the default model (hard cap $0.10 at ledger
prices) and show them verbatim with your sentence-by-sentence grounding check. If you propose a
stronger model, also show the same 7 days with it (hard cap $0.50) and the cost per day.
Never write to production. Commit plan, tasks and dry-run results to your branch, push, stop.

## Checkpoint 2 - implementation (after approval)

Test-first, small commits, no provider calls in tests. Full gate in a clean copy with PostgreSQL as in
CI (`make lint PYTHON=...`, full pytest, `bash -n scripts/*.sh`). Open a PR to `master` (do not merge)
with screenshots of `/` for a normal day (10-16), a quiet day (10-18) and a missing-brief day, desktop
and mobile. Stop and report: what changed, gate results, cost per day, deviations from the plan.

## Rules

- Backward compatible API (only optional fields added); existing 006 behaviour unchanged otherwise.
- No provider calls on page load; brief failure never breaks `/` or the job.
- Do not change deploy defaults, timers, auth or retention. Never touch production.
- Files ASCII; comments only where non-obvious.
- New non-obvious failures -> `docs/troubleshooting.md`.
- Prompts for other sessions -> `docs/prompt-<task>-<YYYY-MM-DD>.md`.
