# Prompt: 007 Daily Signals Brief - research and plan (Phase A, 2026-10-19)

You are the **planner** for feature `007-daily-signals-brief` in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, FastAPI, Typer, SQLAlchemy/Alembic;
production on PostgreSQL). It is a small iteration on the live Daily AI Signals block (006).
You plan only; a different session implements after the coordinator reviews your plan.
Do not write application code. Stop at the end of this prompt.

## Work in your own worktree

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-007-plan -b plan/007-daily-signals-brief origin/master
cd ../AI_PARSER-007-plan
```

Do not work in the main folder. Use `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1`, no `.env` in
the worktree for tests (see `docs/troubleshooting.md`).

## Read first

1. `AGENTS.md`, `docs/troubleshooting.md`
2. `.specify/specs/007-daily-signals-brief/spec.md` (contract; section Decisions D1-D3 is final)
3. 006 context: `.specify/specs/006-daily-ai-signals/plan.md` (Decisions 1-7, Deferred),
   `dry-run.md` sections 8-11, `docs/daily-signals.md`
4. Code: `src/app/core/daily_signals*.py`, `src/app/storage/daily_signals*.py`,
   `src/app/web/signals_view.py`, `src/app/web/models.py`, `src/app/web/digest.html`,
   `src/app/core/weekly_narrative.py` (grounded narrative pattern to reuse),
   `src/app/config/settings.py` (model settings)
5. Live block: `https://5kzt.l.time4vps.cloud/?date=2026-10-16` and `?date=2026-10-17`;
   API `https://5kzt.l.time4vps.cloud/api/news/daily-signals?date=2026-10-16`

## Step 1 - research (short, sourced)

Study how established news products present a daily brief and unverified items, and bring back
what applies here. Suggested sources: Techmeme (clustering, "more" folding), Axios Smart Brevity,
TLDR / Ben's Bites / The Batch (AI daily newsletters), Google News / Ground News (coverage counts),
newsroom verification labels (Reuters, AP: "unconfirmed", "single source"), plus any LLM-summary
grounding practice you find useful. Output `research.md` in the spec folder, max ~1.5 pages:
findings with links, and for each spec item (brief shape, one-liners, D3 confirmed vs single
source, spike folding, chips, quiet day) the practice you recommend and why. For D3 propose
exactly one option with an ASCII wireframe; the coordinator's hypothesis in the spec is a starting
point, not a requirement.

## Step 2 - plan

Write `plan.md` and `tasks.md` in `.specify/specs/007-daily-signals-brief/` (format as in 006, much
shorter): brief prompt and JSON schema, validation, storage and versioning, one-liner rule, noise
rules with exact constants, quiet-day rendering, API fields, UI wireframe (ASCII), job integration,
tests, cost. Confirm the exact id and prices of the stronger DeepSeek model from the DeepSeek API
docs and record them with the date (the brief model is a setting; extraction stays
`deepseek-flash`).

## Step 3 - dry-run

On a local scratch copy with the production snapshots of 2026-10-12..18 (import via the public API
`GET /api/news/daily-signals?date=` and `GET /api/news/digests?date=`; read-only), generate briefs
for those 7 days with the stronger model (hard cap $0.50 at ledger prices) and with
`deepseek-flash` (hard cap $0.10). Show both verbatim side by side with a sentence-by-sentence
grounding check and cost per day. Also show the one-liners and the folded New/spikes/chips for
10-16 and the quiet-day block for 10-18 as text renders. Use a throwaway script under `tmp/`;
do not commit it into `src/`.

Never write to production. Commit `research.md`, `plan.md`, `tasks.md` and `dry-run.md` to your
branch, push, stop, and report: recommended D3 option, the model comparison, cost per day, open
risks.

## Rules

- Planning only: no changes under `src/`, `tests/`, `scripts/`, deploy files.
- Do not change deploy defaults, timers, auth or retention. Never touch production.
- Files ASCII; keep documents short.
- Prompts for other sessions -> `docs/prompt-<task>-<YYYY-MM-DD>.md`.
