---
description: "Tasks: weekly and monthly AI signals (017)"
---

# Tasks: Weekly and Monthly AI Signals

**Input**: `specs/017-weekly-monthly-signals/spec.md`, `plan.md`
**Prerequisites**: owner answers Q1-Q4 in `plan.md` (T-F1 only if Q1 is no).

One task = one PR, in this order. Each PR: worktree off `origin/master`; the code doc
`src/app/core/periodic/signals_period.md` is edited first and matches the code at the end of the PR;
scoped checks while working, then the full gate before push (`make lint PYTHON=./venv1/bin/python`,
`./venv1/bin/pytest`, `./venv1/bin/python scripts/check_code_docs.py`). Do not merge; deploys are the
owner's. `check_code_docs.py` fails on names that do not exist yet: each PR adds to the doc only the
rules, names, tests and `covers` globs it ships.

## Format: `[ID] [Story] Description`

## Phase 1: Cleanup stage 1, weekly v2 code (US3, G5) - one PR (release R1)

- [x] T001 [US3] Re-read prod facts read-only (rows and size of `weekly_*`, crontab has no weekly
  line, `weekly_input_observations` growth) and put them in the PR body.
- [x] T002 [US3] Remove collection hooks: `_record_weekly_observation` calls in
  `core/ingestion/pipeline/rss.py` and `html_links.py`; `record_attempt` and source-version
  registration in `cycle.py`; v2 branch in `weekly_hooks.py` (legacy Monday publish stays). Edit
  `core/ingestion/pipeline.md` first ("Weekly hooks", the F1 decision line, test names).
- [x] T003 [US3] Delete `src/app/core/weekly/`, `src/app/storage/weekly.py`; drop the
  `WeeklyStore` calls in `WeeklyAnalyticsRepo.save_weekly_report` (`storage/repos.py`); remove the
  `weekly-analytics` and `weekly-analytics-audit` commands and v2 imports from `cli/main.py`.
- [x] T004 [US3] Remove the 17 v2 fields from `config/settings.py` (check `weekly_publisher_overrides`
  has no other user); delete `scripts/run_weekly_analytics_job.sh`, `scripts/weekly_frozen_report.py`;
  `scripts/deploy_prod.sh`: drop the cron install, keep removal of a stale managed block.
- [x] T005 [US3] Remove `AINEWS_WEEKLY_V2_ENABLED` from both deploy workflows (keep it in the `.env`
  strip patterns), `docker-compose.prod.yml`, `deploy/.env.prod.example`, `docs/deploy.md`,
  `docs/configuration.md`; delete `docs/weekly-analytics.md`; fix `docs/README.md`, `README.md`,
  `src/app/README.md`, `docs/troubleshooting.md`, `web/pages.md`.
- [x] T006 [US3] Tests: delete the 6 `tests/unit/test_weekly_*.py` and
  `tests/integration/test_weekly_postgres.py`; edit v2 assertions in `test_pipeline_runtime.py`,
  `test_deploy_cron_image.py`, `test_deepseek_deploy_workflows.py`, `test_web_weekly_analytics.py`.
  Leave model classes and tables. Add a test that a fetch cycle writes no `weekly_*` row.
  `bash -n scripts/*.sh`.
- [x] T-F1 [US3] Not needed (Q1 answered yes, 2026-10-28). Only if Q1 were no (v2 kept): `cycle.py` `fetch_failure` -> `complete=False`, test
  expects it; skip T002-T006 deletions.

**Checkpoint**: legacy Monday report and `/` preview unchanged; no `weekly_*` writes.

## Phase 2: Numbers (US1) - MVP, two PRs (release R2)

- [ ] T010 [US1] Code doc first: create `src/app/core/periodic/signals_period.md` (header, Behavior
  for definitions, status and coverage rules, sections, Decisions from `plan.md`, Invariants, Code
  map); register in `docs/README.md`, `README.md`, `src/app/README.md`. Create the package with
  `period_model.py` (`PeriodThresholds`, `PeriodInput`, bounds of week/month, status) and tests for
  bounds (year change, Monday start) and status precedence.
- [ ] T011 [US1] Extract `trend_delta` from `core/daily/signals_compute.py` with no behavior change;
  daily tests and fixture payload hashes unchanged (no `METHODOLOGY_VERSION` bump). Verify whether the
  daily window includes D; document it.
- [ ] T012 [US1] `period_compute.py` (pure): top stories merge across days, top entities by group,
  new union, weekly risers/coolers from the Sunday snapshot or the helper, event mix and delta,
  publisher breadth suppression, coverage line, `payload_hash`. Fixture weeks built from
  `tests/fixtures/daily_signals/`; one test per rule named in the doc.
- [ ] T013 [US1] Storage: `PeriodSignalReport`, `PeriodSignalBrief` models, migration
  (`down_revision` = current head, skips objects `create_all()` made), `storage/period_signals.py`
  `PeriodSignalRepo` (load inputs, upsert if hash changed, read latest, index). Migration test;
  test "writes only its own tables".
- [ ] T014 [US1] CLI `ai-news period-signals` (`--kind`, `--period`, `--backfill`, `--recompute-all`),
  flag `AINEWS_PERIOD_SIGNALS_ENABLED`; JSON run report; step in `scripts/run_daily_digest_job.sh`
  with the same guards as daily signals; `bash -n`. `docs/period-signals.md` (operator commands,
  rollback) registered in `docs/README.md`.
- [ ] T015 [US1] API `GET /api/news/period-signals` and `/index` in `web/routes/period.py` and
  `web/models.py` (new models only); unavailable/corrupt row gives 200 with a state; route table test
  updated.

## Phase 3: Page (US1) (release R3)

- [ ] T020 [US1] `web/period_view.py`, `period.html`, `static/js/period.js`, `static/css/period.css`;
  `GET /weekly` with `?week=`; escaped output, http(s) links only; nav link only when a period exists;
  one-line link on `/` below the signals block (legacy preview stays). Update `web/pages.md`
  (Behavior, tests), `packaging` data test, tests for unavailable, partial and corrupt states.
- [ ] T021 [US1] Operator verification (read-only prod after deploy): enable flag, `--backfill 3`,
  compare the three weeks to the daily pages by hand; record in `records/`.

## Phase 4: Brief (US2) (release R4, after Q2 = yes)

- [ ] T030 [US2] Doc first (Behavior for the brief, cost, flags). Parameterise packet and
  `parse_brief` in `signals_brief.py` for sentence counts without changing daily behavior (daily tests
  unchanged). `period_brief.py` packet (cap), prompt, `PERIOD_BRIEF_VERSION`, input hash.
- [ ] T031 [US2] Brief step in the CLI under `AINEWS_PERIOD_SIGNALS_BRIEF_ENABLED`, through
  `SignalsLedger` with its own run id, `--max-usd`, per-brief cap, unpriced-model skip; tests with
  `MockTransport` (ok, invalid after one recovery, cached by hash, cap, flag off creates no provider).
  Page/API show the brief with numbered links and the AI note.
- [ ] T032 [US2] Dry run on the three weeks with a small `--max-usd`; record real cost and quality in
  `records/` and in the doc; then the owner turns the flag on.

## Phase 5: Retire legacy weekly (US3) (release R5)

- [x] T040 [US3] Stop the Monday legacy publish: delete `weekly_hooks.py` and its test; replace the
  preview section in `digest.html`/`digest.js`/`digest.css` by the link; `/weekly-ai-analytics*`
  answer 308 to `/weekly`; delete the two legacy pages and nav links; keep the legacy API and tables.
  Update `web/pages.md`, `pipeline.md`, route table test, `docs/README.md`.
- [ ] T041 [US3] One release later, after a verified restore of the latest dump (record it):
  migration dropping the 8 v2 tables (`IF EXISTS`; downgrade recreates empty), delete their model
  classes. Confirm `create_all()` and the migration chain on SQLite and PostgreSQL.

## Phase 6: Monthly (US4) (release R6, before 2026-12-01)

- [ ] T050 [US4] Doc first (month rules). Month bounds, `month_*` thresholds, month risers via
  `trend_delta`, month event mix; `--kind month`, nightly default on the 1st; `GET /monthly`, nav
  link when a month exists. Tests for 28/29/30/31-day months, partial October, no comparison
  without a ready previous month.

## Dependencies and order

- Phase 1 is independent of 2-4 (may ship first or in parallel; recommended first: it stops the
  growth). Phase 2 before 3, 3 before 4 and 5, 5 (T040) only after the page is live. T041 at least
  one release after Phase 1. Phase 6 after Phase 3.
- Parallel: T001-T006 with T010-T011 (different files).

## Notes

- Every question that is not product or money is already decided in `plan.md`; the implementer
  records new findings in the doc as "decided <date> (agent): ..." and notifies the owner.
- Never settle silently: a changed threshold, a changed public URL or a cost above the caps goes to
  the owner as a yes/no with a recommendation.
