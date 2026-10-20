# Prompt: 007 Daily Signals Brief - implementation (Phase B, 2026-10-19)

You are the **implementer** for feature `007-daily-signals-brief` in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, FastAPI, Typer, SQLAlchemy/Alembic;
production on PostgreSQL). The plan is approved; a coordinator session reviews your work at each
checkpoint. Stop at every checkpoint.

## Work in your own worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-007-impl -b feat/007-daily-signals-brief origin/master
cd ../AI_PARSER-007-impl
```

Do not work in the main folder or in `../AI_PARSER-007-plan` (read-only for you: it holds the
dry-run fixtures). Use `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1`; no `.env` in the
worktree for tests (see `docs/troubleshooting.md`).

## Read first

1. `AGENTS.md`, `docs/troubleshooting.md`
2. `specs/007-daily-signals-brief/`: `spec.md` (contract), `plan.md` (revision 2 plus the
   coordinator's O1 adoption: prompt `daily-signals-brief-3`), `tasks.md` (your work list),
   `research.md`, `dry-run.md`
3. 006: `specs/006-daily-ai-signals/plan.md`, `docs/daily-signals.md`
4. Code named in `plan.md` and `tasks.md`

## Checkpoint 1 - Phases 0-3 (stop)

T0.1 first: copy fixtures from
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-007-plan/tmp/007-brief-dryrun/` as T0.1 says (never
invent provider answers). Then T1.1-T3.2, test first, a commit per phase, each after
`make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python` and the full pytest.
Push and report: commits, test counts, any deviation from the plan and why.

## Checkpoint 2 - Phases 4-5 (after approval)

T4.1-T5.3. T5.2 is the only real provider spend (cap $0.50 at ledger prices). Full gate in a clean
copy with PostgreSQL as in CI. Open a PR to `master` (do not merge) with screenshots of `/` for
10-16 (normal), 10-18 (quiet) and a missing-brief day, desktop and 375 px. Stop and report: what
changed, gate results, T5.2 results (SC-001..SC-003, SC-005, O1 effect on 10-16), cost per day,
deviations.

## Rules

- Backward compatible API (only optional fields); 006 behaviour otherwise unchanged.
- No provider calls in tests or on page load; a brief failure never breaks `/`, the digest or the
  extraction result.
- `--max-usd` is the total for a run (extraction + briefs).
- Do not change deploy defaults, timers, auth or retention. Never touch production.
- Files ASCII; comments only where non-obvious; new non-obvious failures ->
  `docs/troubleshooting.md` in the same change.
- Prompts for other sessions -> `docs/prompt-<task>-<YYYY-MM-DD>.md`.
