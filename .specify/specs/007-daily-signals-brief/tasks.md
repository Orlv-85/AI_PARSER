# Tasks: Daily Signals Brief and Readability

**Input**: `spec.md`, `plan.md` (revision 2), `research.md`, `dry-run.md` in
`.specify/specs/007-daily-signals-brief/`
**Branch**: `feat/007-daily-signals-brief`
**Rules**:
- Start only after the coordinator approves the plan. Owner decisions D1-D3 (spec) and plan P1-P6 are
  final unless the coordinator changes them.
- Test first in every task. No provider calls in tests (fake `httpx.MockTransport`).
- Commit per phase, each after `make lint PYTHON=./venv1/bin/python` and `./venv1/bin/pytest` with
  PostgreSQL as in CI (`docs/troubleshooting.md`: clean copy without `.env`,
  `local-suite-skips-postgres-integration`).
- Files ASCII. Real provider spend only in T5.2 (cap $0.50 at ledger prices, `--max-usd`).
- No change to extraction (`daily-signals-extract-5`), identity rules, New gate thresholds,
  Rising/Cooling math, deploy defaults, timers, auth or retention.

## Format

`[ID] [P?] Title` - **Files** / **Test first** / **Done when** / **Depends on**.

---

## Phase 0: Fixtures

- [ ] **T0.1 Dry-run fixtures**
  - Files: `tests/fixtures/daily_signals/brief/` - `sig-2026-10-12..18.json`, `dig-2026-10-12..18.json`
    (public API answers, renamed from `sig-DD.json` / `dig-DD.json`), `responses.json` (all 37 raw
    provider answers, keyed by request hash), `answers.json` (per day and model: packet, attempts
    with codes, accepted sentences), `report-rev2.json` (brief-2 packets and answers, 3 days), `one_liners.json` (40 expected lines and sources), short `README`
    (origin, dates).
  - Steps: copy from `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-007-plan/tmp/007-brief-dryrun/`
    (planning worktree, gitignored; keep it until T0.1 is done); if missing, re-fetch the public API
    answers and stop for the provider answers (never invent them).
  - Depends on: -

## Phase 1: Pure core

- [ ] **T1.1 [P] Brief packet, body and validation**
  - Files: `src/app/core/daily_signals_brief.py`, `tests/unit/test_daily_signals_brief.py`
  - Test first: packet ids and links from a stored payload + digest items; quiet-day input (all items,
    max 30); 12,000-byte shrink; `input_hash` changes with packet, version or model; body pinned
    (prompt `daily-signals-brief-3`, thinking disabled, 900 tokens); O1 review marker (10-15
    comparison story and 10-16 Surface story marked, no news story of 10-12..16 marked); every validation code of plan
    rules 1-9 with a minimal failing answer; the 3 brief-2 answers pass; of the 14 revision-1 answers
    10 pass and 4 fail with `same_story`; the 3 rejected first attempts fail with their codes;
    recovery suffix text.
  - Done when: tests pass.
  - Depends on: T0.1

- [ ] **T1.2 [P] One-liners**
  - Files: `src/app/core/daily_signals_compute.py`, `tests/unit/test_daily_signals_compute.py`
  - Test first: sentence split (Oct., U.S., Inc.), name match (FLUX.3 vs FLUX 3), WHAT verbs
    (`Codex-built` is not `built`), < 8-word quote rule, 140-char cut; the 40 fixture items give the
    expected line and source.
  - Done when: `one_liner`, `one_liner_source` in the payload for every New item.
  - Depends on: T0.1, T2.1 (the `summary` field; a stub `ArticleObs.summary` default `""` first)

- [ ] **T1.3 [P] Noise rules and quiet flag**
  - Files: `src/app/core/daily_signals_compute.py`, `tests/unit/test_daily_signals_compute.py`
  - Test first: variant rule (GPT, NVIDIA Nemotron on a dataset, Muse Spark, DeepSeek-V4.1-Flash, other
    entity type); folding into a story by entity, by label and by vendor; into New by vendor; into an
    earlier spike; diffuse company spike dropped; a spike sharing links with a story that does not name
    it stays (GPT-6 Astra case); reason = largest D story; `spikes_folded` recorded; `quiet` for items
    < 20 and for no top story; thresholds recorded; `METHODOLOGY_VERSION = "daily-signals-3"`; payload
    hash unchanged on a second compute.
  - Depends on: -

## Phase 2: Storage, ledger, settings

- [ ] **T2.1 Digest summary in observations**
  - Files: `src/app/storage/daily_signals.py`, `tests/unit/test_daily_signals_repo.py`
  - Test first: `ArticleObs.summary` is the digest item summary of that day's item URL; a URL in two
    digests gets each day's summary; no digest summary -> `""`.
  - Depends on: -

- [ ] **T2.2 `daily_signal_briefs` table and repo**
  - Files: `src/app/storage/models_sql.py`, new Alembic revision after `b6d1f0a7c3e5`,
    `src/app/storage/daily_signals.py`, `tests/unit/test_daily_signals_migration.py`,
    `tests/unit/test_daily_signals_repo.py`, PostgreSQL integration test if the 006 ones cover tables
  - Test first: upgrade/downgrade (no FK to articles; legacy cleanup guard unchanged); `save_brief`
    upsert by day; `get_brief`.
  - Depends on: -

- [ ] **T2.3 Per-model ledger prices and brief settings**
  - Files: `src/app/storage/daily_signals_ledger.py`, `src/app/config/settings.py`,
    `tests/unit/test_daily_signals_ledger.py`, settings tests
  - Test first: `prices` parameter used for actual and reservation; default equals today's flash
    prices (006 behaviour unchanged); `daily_signals_brief_model` default `deepseek-v4-pro`; unknown
    model has no price entry.
  - Depends on: -

## Phase 3: Orchestration and CLI

- [ ] **T3.1 Brief step in `run_signals`**
  - Files: `src/app/core/daily_signals.py`, `tests/unit/test_daily_signals_run.py`
  - Test first (MockTransport): disabled / missing key / recompute-only -> 0 brief calls; one-day run
    -> 1 call, row `ok`; rerun -> 0 calls (same input hash); changed snapshot -> 1 call; invalid then
    valid -> 2 calls, `ok`; invalid twice -> row `invalid`; LedgerStop (cap/deadline) -> extraction
    state unchanged, `report["brief"]` says why; D-1 catch-up; backfill range; `--max-usd` is the run
    total (plan R2): brief cap `min(0.05 * days, X - extraction spend)`, extraction spend >= X ->
    `skipped:brief_budget_exhausted` and no brief ledger row, extraction + brief spend <= X, nightly
    run uses `settings.daily_signals_max_usd` the same way; unknown model -> `brief_model_unpriced`, no call; run report has no
    key and no article text.
  - Depends on: T1.1, T1.3, T2.2, T2.3

- [ ] **T3.2 CLI and run report**
  - Files: `src/app/cli/main.py` (no new flags expected), `tests/unit/test_cli_daily_signals.py`
  - Test first: JSON line includes the `brief` block; exit codes unchanged.
  - Depends on: T3.1

## Phase 4: API and UI

- [ ] **T4.1 API fields**
  - Files: `src/app/web/models.py`, `src/app/web/app.py`, `tests/unit/test_web_daily_signals_api.py`
  - Test first: a 006 payload validates with the same fields and defaults; `brief` attached from an
    `ok` row; `invalid`, missing or unreadable row -> `brief: null` (error log for unreadable JSON);
    storage error behaviour as in 006.
  - Depends on: T2.2

- [ ] **T4.2 Server and client render**
  - Files: `src/app/web/signals_view.py`, `src/app/web/digest.html`,
    `tests/unit/test_web_public_digest.py`
  - Test first: brief list escaped (`<script>`), `[n]` links http(s) only, AI note present; D3 (no
    `early signal`, "N outlets" / "via publisher", muted class); one-liner (quote-sourced in quotes);
    variant line only when present; story spike tag; spike reason line; Spikes card hidden when empty
    in `spikes_only`; chips hard types + "+N more"; quiet render (template line, no story/spike
    cards); page 200 with a corrupt brief row; client `renderSignals` has the same classes.
  - Depends on: T4.1

- [ ] **T4.3 Manual UI check**
  - Steps: scratch SQLite as in 006 T5.3, seed reports and brief rows from the T0.1 fixtures; desktop
    and 375 px; 10-16, 10-15, 10-18; date switching. Notes in the PR.
  - Depends on: T4.2

## Phase 5: Docs, validation, rollout

- [ ] **T5.1 Docs**
  - Files: `docs/daily-signals.md` (brief, one-liners, noise rules, quiet day, cost table, model
    setting, backfill example, rollback: the flag stops briefs; table kept on code revert),
    `docs/configuration.md`
  - Depends on: T3.2

- [ ] **T5.2 Validation on real data (cap $0.50)**
  - Steps: scratch copy as in 006 section 9 (local DB + public digests 2026-10-10..18), migrate,
    `--recompute-only` then one paid run per day with `--max-usd`; dump briefs, one-liners, folding.
    Manual check of every brief sentence against its sources (same rubric as `dry-run.md` section 2)
    and of every displayed New one-liner.
  - Done when: `dry-run.md` section 5 added: SC-001..SC-003 and SC-005 met or explained; spend.
  - Depends on: T4.2

- [ ] **T5.3 Gate and PR**
  - Steps: full gate incl. PostgreSQL; PR with migration note (006 deploy race), backfill command for
    2026-10-10..18 (owner-run, `--max-usd 0.45` as the run total), recompute after deploy
    (`--recompute-all` for the methodology bump).
  - Depends on: T5.1, T5.2

## Dependency summary

T0.1 -> T1.1, T1.2; T2.1 -> T1.2; T1.1 + T1.3 + T2.2 + T2.3 -> T3.1 -> T3.2 -> T5.1;
T2.2 -> T4.1 -> T4.2 -> T4.3, T5.2 -> T5.3.
