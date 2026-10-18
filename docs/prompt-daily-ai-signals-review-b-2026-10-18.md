# Prompt: Independent review B of PR #39 - web, security, job, production safety (2026-10-18)

You are an independent READ-ONLY reviewer for PR #39 (`feat/006-daily-ai-signals`) in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, FastAPI, Typer, SQLAlchemy/Alembic;
SQLite local, PostgreSQL in production behind Caddy; daily systemd timers). Another reviewer (A)
covers the data/compute/storage path; you cover what touches users and production. You did not write
this code. Find real defects; do not rewrite style.

## Setup (do not work in the main folder; another session uses it)

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
SHA=$(gh pr view 39 --json headRefOid -q .headRefOid)
git worktree add --detach ../AI_PARSER-review-b "$SHA"
cd ../AI_PARSER-review-b
```

Record `$SHA` in your report. Tests: use `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1` with
`PYTHONPATH=src` and no `.env` in the worktree (see `docs/troubleshooting.md`). No provider calls, no
production access, no network writes. You may run the app locally on a free port with explicit env.

## Read first

`AGENTS.md` (Deploy And Ops, Web And Runtime sections); `.specify/specs/006-daily-ai-signals/spec.md`,
`plan.md` (UI, API Contract, Job Integration, Rollout and Rollback); `docs/daily-signals.md`;
`gh pr view 39` and `gh pr diff 39`. Context: PR #38 (merged) made all non-GET/HEAD methods on
`/api/` require auth; the publish token only covers two POST endpoints.

## Scope (focus here)

- `src/app/web/app.py`, `signals_view.py`, `models.py`, `digest.html`:
  - XSS: every rendered field escaped server-side and client-side; links only http(s); quotes and
    labels from article text are untrusted; attribute contexts; JSON embedded in HTML.
  - Auth: `GET /api/news/daily-signals` public, other methods 401 with auth enabled; nothing else
    became public; no admin data leaks in the payload.
  - Failure isolation: signals read errors never break `/` (status 200 with digest); no provider code
    on the request path; performance of the added read (one indexed row).
  - Client JS: date change races, stale responses, error states, no console errors; mobile layout.
- `scripts/run_daily_digest_job.sh`: lock handling and re-exec, `set -eu` paths, time budget math vs
  `TimeoutStartSec`, outer `timeout -k`, container name collisions and cleanup, exit codes (digest
  result decides the job; signals failure never fails the job), behaviour when `timeout` is missing,
  relative-path start, quoting. Run `bash -n` and, where feasible, the job tests.
- `docker-compose.prod.yml` line and settings defaults: flag default false, no other default changed
  (ports, auth, retention, DB). Compare with `deploy/`, workflows and `docs/deploy.md`.
- Migration safety on deploy: `scripts/deploy_prod.sh` starts the app before `alembic upgrade head`
  and routes call `create_all()` - can the first deploy break or leave a half-created schema? Is the
  documented recovery correct?
- Rollout/rollback in the PR description and `docs/daily-signals.md`: are the steps complete, in the
  right order, and reversible without touching digest/weekly data?
- Logs and reports: no secrets or article bodies written; file permissions of run reports and ledger.

## Method

1. Read the diff against plan and AGENTS.md rules; list every production-sensitive change.
2. For each suspected defect, build a concrete failure scenario and, where cheap, prove it (local
   request with crafted data, shell test with fake `docker`/`timeout` on PATH). Do not commit.
3. Run the web/job tests and the full suite once (clean environment); report exact results.

## Output

Write `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/daily-ai-signals-pr39-review-b-2026-10-18.md`
(do not commit; do not touch other files in the main folder):

- Header: SHA reviewed, what you ran and results.
- Findings table sorted by severity: ID (B01...), severity (blocker / major / minor / nit),
  file:line, one-sentence defect, concrete failure scenario, evidence, suggested fix (short),
  confidence (confirmed / plausible).
- "Verified OK" list of risky areas checked and found correct.
- Verdict: merge-ready / merge after fixes / rework.

Stop after writing the report. Do not fix code, push, comment on the PR or remove the worktree.
