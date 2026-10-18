# Prompt: Daily AI Signals - Phase B (implementation) (2026-10-18)

You are the IMPLEMENTER session for feature `006-daily-ai-signals` in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (ai-news-collector, Python 3.14, FastAPI + Typer +
SQLAlchemy/Alembic). You did not write the plan; a planning session did, and a coordinator session
reviewed it. The coordinator reviews your work at each checkpoint below. Stop at every checkpoint.

Branch: `feat/006-daily-ai-signals` (already checked out in this folder; contains spec, plan, reviews).
A separate session may be working in `../AI_PARSER-authfix` on another branch; do not touch it.

## Read first (mandatory, in this order)

1. `AGENTS.md`, `docs/troubleshooting.md`
2. `.specify/specs/006-daily-ai-signals/spec.md` (contract)
3. `.specify/specs/006-daily-ai-signals/plan.md` (revision 4) and `tasks.md`
4. `.specify/specs/006-daily-ai-signals/dry-run.md` (real-data findings, rubric context)
5. `docs/daily-ai-signals-phase-a-coordinator-review-2026-10-18.md` - **binding changes C1 and C2**
6. Raw dry-run data and fixtures: `tmp/daily-signals-dryrun/` (gitignored; scripts, digests, fixtures)

## Owner decisions (final)

- OD1-OD7: plan defaults accepted as written in plan.md "Owner Decisions Required".
- SD1-SD13: accepted (incl. SD4 `is_new`/`is_new_quote`, types `hardware`/`policy`; SD6 event counts
  per story).
- Budgets: validation $2.50 total (prompt gate + later history validation); production backfill cap
  $3.00 (owner-run later). The one-line `docker-compose.prod.yml` change is approved (flag default
  false). The owner flips `AINEWS_DAILY_SIGNALS_ENABLED` in production; you never do.
- Coordinator changes accepted by the owner: C1 (prompt gate first) and C2 (MVP scope cut).

## Step B0 - Update the plan (one docs commit)

Edit `plan.md` and `tasks.md` (do not edit `spec.md`; spec deltas stay in plan.md):
- Record the owner decisions above (replace "Owner Decisions Required" with "Owner Decisions (final)").
- Add a new first phase "Prompt gate" (see B1) before Phase 0; Phase 7 stage 1 becomes redundant -
  keep Phase 7 only for history validation (stage 2) and the final review.
- Apply C2: move the deferred items into a "Deferred (not in first release)" section, each with the
  trigger that would bring it back:
  - ledger: budget ids, lifetime per-scope-day USD cap, attempt keys / per-content-hash attempt limits,
    `reset-attempts`, the 80 s watchdog thread. Keep: one POST per attempt, replay of saved 200
    responses, per-run caps (calls, USD with reservation and actual usage, app-side deadline checked
    before each POST, httpx timeouts), stop after 3 consecutive failures. Budgets for validation and
    backfill are enforced per invocation with `--max-usd`.
  - entities: `split` override, `ai_entity_candidates` table, `suspects` command. Keep normalization,
    stoplist, vendor classes, base/family keys, pure `reconcile`, shared `?` entity, `merge` + `alias`
    overrides with stable selectors.
  - Update tables, modules, tests, CLI, data model, traceability and task dependencies accordingly.
    Keep everything else in the plan (evidence table without FK, identity, recompute, job script, API,
    UI).
- Commit: `docs(spec): apply owner decisions and coordinator review to 006 plan`.

## Step B1 - Prompt gate (then STOP - checkpoint 1)

Purpose: prove that prompt v3 makes "New" good enough before building anything.

- Throwaway script in `tmp/daily-signals-gate/` (not committed). Input: local `data/ai_news.db`
  joined to the public digests for 2026-10-12..16 exactly as in the dry-run (369 items). Use the exact
  v3 request body, system prompt and validation rules from plan Decision 1, **one call per article**,
  content up to 6,000 chars. Key from local `.env` (`DS_API_KEY`); never print it.
- Spend: hard stop at $1.00 for the gate (part of the $2.50 validation budget); log calls, tokens,
  cost. Cache responses on disk so a re-run with the same prompt costs nothing.
- First-seen for the gate: extracted target days plus the dry-run's background check against
  2026-08-03..10-11 titles/summaries (deterministic order this time). Apply the plan's identity rules
  (Decision 2, as far as needed to judge New) and the New gate (Decision 5).
- Review every displayed New item with the T7.2 rubric (OK / BAD-retrospective / BAD-established /
  BAD-generic / BAD-non-AI / BAD-identity / uncertain; does the quote state a launch?) and measure
  recall as T7.2 defines it. Also show Top stories per day.
- Pass bar: New precision >= 80% OK and <= 10% BAD over the 5 days; no generic, non-AI or
  established-company items; Moltbook (10-13) and Attie (10-15) not New; Muse Spark Open New on 10-15;
  Elorian Glimpse New on 10-16; Beam not New on 10-16.
- If the bar is missed: you may revise the prompt (bump the version string) at most twice within the
  $1.00 gate limit; record each revision and its effect.
- Write results to `.specify/specs/006-daily-ai-signals/prompt-gate.md` (per-day tables, verdicts,
  precision/recall, spend, final prompt text if changed) and update plan Decision 1 if the prompt
  changed. Commit both.

**Checkpoint 1: stop and report** (precision, recall, spend, notable failures, final prompt version).
Do not start B2 until the owner explicitly says to continue.

## Step B2 - Build (after approval of checkpoint 1)

Follow the updated `tasks.md`: test first, no provider calls in tests, commit per phase after the full
gate (`make lint PYTHON=./venv1/bin/python`, `./venv1/bin/pytest`).

- Phases 0-3 (fixtures, pure core, storage + migration, ledger/orchestration/settings/CLI).
  **Checkpoint 2: stop**, push the branch, report what was built, test counts, open issues.
- Phases 4-6 (API, main-page UI, job script, compose line, docs). Open a PR to `master` (do not merge).
  **Checkpoint 3: stop** and report; include screenshots or rendered HTML of `/` for states
  ready / partial / unavailable (local run with explicit env, do not change runtime defaults).
- Phase 7 (history validation on a scratch DB, within the remaining validation budget) only after the
  coordinator approves checkpoint 3. Phase 8 rollout is owner-run; you only prepare the checklist.

## Hard rules

- Never write to production, never deploy, never change timers or the server `.env`.
- Paid provider calls only in B1 and Phase 7, within the stated limits.
- Do not change existing CLI flags, API responses, digest/weekly storage or deploy defaults beyond the
  plan and the approved compose line.
- Keep files ASCII; match surrounding code style; comments only where non-obvious.
- If you disagree with the plan, stop and explain at the next checkpoint instead of silently diverging.
- New non-obvious failures -> add a case to `docs/troubleshooting.md`.
- Any prompt you write for another session -> `docs/prompt-<task>-<YYYY-MM-DD>.md`, linked in your reply.

## At every checkpoint, reply with

What changed (file links), how it was validated (exact commands and results; never claim full
validation if only scoped checks ran), spend so far, deviations from the plan, open questions.
