# Prompt: Independent review A of PR #39 - correctness, data, storage, money (2026-10-18)

You are an independent READ-ONLY reviewer for PR #39 (`feat/006-daily-ai-signals`) in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, FastAPI, Typer, SQLAlchemy/Alembic;
SQLite local, PostgreSQL in production). Another reviewer (B) covers web/security/ops; you cover the
data path. You did not write this code. Find real defects; do not rewrite style.

## Setup (do not work in the main folder; another session uses it)

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
SHA=$(gh pr view 39 --json headRefOid -q .headRefOid)
git worktree add --detach ../AI_PARSER-review-a "$SHA"
cd ../AI_PARSER-review-a
```

Record `$SHA` in your report. Tests: use `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1` with
`PYTHONPATH=src` and no `.env` in the worktree (see `docs/troubleshooting.md`). No provider calls, no
network writes, no production access.

## Read first

`AGENTS.md`; `.specify/specs/006-daily-ai-signals/spec.md`, `plan.md` (final), `tasks.md`,
`prompt-gate.md`; `docs/daily-ai-signals-phase-a-coordinator-review-2026-10-18.md`;
`gh pr view 39` and `gh pr diff 39`.

## Scope (focus here)

- `src/app/core/daily_signals_entities.py` - normalization, keys, vendor classes, reconcile purity
  and order independence, overrides (merge/alias) and selector stability.
- `src/app/core/daily_signals_extract.py` - request body, validation rules, grounding, quote and
  retrospective checks, recovery/retry keys, injection handling of article text.
- `src/app/core/daily_signals_compute.py` - New gate, family suppression, clustering, spikes,
  rising/cooling windows and readiness, status precedence, payload hash determinism, edge cases
  (empty days, missing days, zero denominators, null published_at, ties).
- `src/app/storage/daily_signals.py`, `models_sql.py` changes, the Alembic migration - constraints,
  indexes, NULL handling in UNIQUE, SQLite vs PostgreSQL differences, CASCADE and retention, evidence
  without FK and (id, url_canonical_hash) identity, upserts and IntegrityError paths, transaction
  boundaries, migration upgrade/downgrade and create_all interaction.
- `src/app/storage/daily_signals_ledger.py` and `src/app/core/daily_signals.py` - spending caps are
  checked before every POST and cannot be exceeded, reservation vs actual cost, replay of cached
  responses, crash/timeout states, deadline handling, resume behaviour, one call per article.
- `legacy_cleanup` guard change (CASCADE allow-list) - can it hide a real unsafe FK?
- CLI `daily-signals` / `daily-signals-entities`: flags, defaults, flag gate (paid extraction only),
  backfill order.
- Tests: do they actually assert the behaviour they name? Missing tests for risky paths.

## Method

1. Read the code against the plan; list every place where behaviour differs from plan or spec.
2. For each suspected defect, build a concrete failure scenario (inputs/state -> wrong result) and,
   where cheap, prove it with a small test or script in the worktree (do not commit).
3. Run the new tests and the full suite once (clean environment); report exact results.

## Output

Write `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/daily-ai-signals-pr39-review-a-2026-10-18.md`
(do not commit; do not touch other files in the main folder):

- Header: SHA reviewed, what you ran and results.
- Findings table sorted by severity: ID (A01...), severity (blocker / major / minor / nit),
  file:line, one-sentence defect, concrete failure scenario, evidence (test/script output or code
  quote), suggested fix (short), confidence (confirmed / plausible).
- "Verified OK" list: risky areas you checked and found correct (so the coordinator knows coverage).
- Verdict: merge-ready / merge after fixes / rework.

Stop after writing the report. Do not fix code, push, comment on the PR or remove the worktree.
