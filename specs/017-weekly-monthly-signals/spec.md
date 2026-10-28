# Feature Specification: Weekly and Monthly AI Signals

**Feature Branch**: `017-weekly-monthly-signals`
**Created**: 2026-10-28
**Status**: Draft (planned 2026-10-28 by the planner; waits for the coordinator's review and the owner's
answers in `plan.md`, section "Owner questions")
**Input**: Backlog B2 and 006 goal G5: weekly and monthly views built on the per-article data layer
of Daily AI Signals (006) and its brief (007). Owner request (paraphrased): "Analytics should help me
stay on top of a fast-moving industry; weekly and monthly later."

## Problem Context

### What exists today (facts read 2026-10-28)

- Daily AI Signals (006) and its brief (007) are live. Prod has per-article extractions, evidence
  (`signal_mentions`, 11,557 rows, 5,988 entities) and one frozen snapshot per day in
  `daily_signal_reports`: 18 days, 2026-10-10 .. 2026-10-27 (methodology `daily-signals-3`), plus 18
  briefs (17 `ok`). Digest-day scope and extraction exist from 2026-07-31, but snapshots only from
  `AINEWS_DAILY_SIGNALS_COMPARABLE_FROM`. Rising/Cooling on `/` is usable since 2026-10-23.
- The weekly block on `/` ("Weekly AI Analytics") and `/weekly-ai-analytics` still show the legacy
  report. The legacy generator is not "off": the fetch cycle publishes a legacy report every Monday
  (`weekly_hooks.py`), the last two on 2026-10-12 and 2026-10-26 (rows for report dates 10-11 and
  10-25). Only the cron job (`run_weekly_analytics_job.sh`) is disabled. Its items are article titles,
  not trends (006 "Why the current analytics does not help").
- Weekly v2 (spec 010: `core/weekly/`, `storage/weekly.py`, `weekly_*` tables) is disabled
  (`AINEWS_WEEKLY_V2_ENABLED=false` in both deploy workflows, compose and `.env.prod.example`) and has
  published nothing to readers: 2 completed jobs and 2 snapshots (report dates 10-04 and 10-11) with 0
  stored model decisions; 4 publication rows, 2 of them only date locks of the legacy Monday report. But its
  collection part still runs on every fetch: one raw observation per item and one coverage attempt per
  source per run (7,139 observations, 2,846 attempts since 2026-10-10; 43 MB of a 182 MB database).
- Details and the keep/delete decision: `plan.md`, "Weekly v2 decision".

### Why a new feature and not weekly v2

Weekly v2 measures shares of 25 frozen broad topics ("attention"). A broad topic is present every
week, so "New" cannot fire; concrete novelties are absorbed into "Open-weight models". Its coverage
gates need 5+ healthy publishers 7/7 days. 006 already solved the unit problem: concrete entities and
event types per article, computed per day, with explainable evidence. The weekly and monthly views
should be sums and comparisons of that data, not a second classification pipeline.

## Goals

- G1. A reader opens one page and sees what happened in the last completed week: the main stories, the
  top entities, what was new, what rose and cooled, and the event mix.
- G2. The same for a calendar month, once a full month of comparable data exists (first: November 2026).
- G3. Everything on the page is explainable: each item links to the days and articles that support it.
- G4. The numbers are deterministic and cost $0; only an optional short brief costs money and is
  capped.
- G5. Weekly v2 stops costing storage and code weight on every fetch run.
- G6. A week or month is shown only when its coverage supports it; otherwise the page says why.

## Non-Goals

- No new extraction or classification: extraction (006) is not changed and not re-run.
- No new provider call for numbers; no model on page loads.
- No watchlists, alerts, personalization, sentiment, market data.
- No change of the daily block, the digest, admission, fetch behavior, auth, ports, retention.
- No reuse of weekly v2 topics or "attention" arithmetic.

## User Scenarios & Testing

### User Story 1 - See last week at a glance (Priority: P1) MVP

As a reader I open `/weekly` and see the last completed Monday-Sunday (UTC) week: top stories, top
entities by type, entities that were new, risers and coolers against the previous week, and the
event-type mix against the previous week. No paid call is needed for any of it.

**Why this priority**: it is the whole reason for B2 and costs $0.

**Independent Test**: seed 14 days of daily snapshots and mentions (fixtures of 006) with one entity
rising and one cooling; `compute_period` returns a ready week with both, and the page renders them
with links to supporting articles.

**Acceptance Scenarios**:

1. **Given** at least `week_min_complete_days` complete days in the week, **When** the week is
   computed, **Then** status is `ready`, with the sections below.
2. **Given** the previous week is also ready and its publisher breadth is comparable, **When** the
   week is computed, **Then** risers, coolers and the event-type delta are shown; **otherwise** they are
   omitted with a one-line reason ("previous week not comparable").
3. **Given** fewer complete days than the minimum, **When** the page is opened, **Then** it shows a
   `partial` or `unavailable` state with the reason and no numbers that need the full week.
4. **Given** a snapshot of one day changed (recompute), **When** the week is recomputed, **Then** the
   stored week changes only if the payload hash changes.

---

### User Story 2 - Weekly brief (Priority: P2)

As a reader I get a 4-6 sentence weekly brief with numbered source links, like the daily brief (007),
checked mechanically and clearly marked as AI-written.

**Why this priority**: useful, but US1 is useful without it; paid, so it ships separately and off.

**Independent Test**: fixture week with a scripted provider answer; a valid answer is stored `ok`, an
invalid one is stored `invalid` after one recovery, and the page shows no brief for it.

**Acceptance Scenarios**:

1. **Given** a ready week and the brief flag on, **When** the paid step runs, **Then** one brief per
   week is stored, keyed by input hash; a second run with the same input makes no call.
2. **Given** the brief flag off or the cap reached, **When** the page loads, **Then** the page shows
   everything else and no brief, never an error.

---

### User Story 3 - Retire the legacy weekly block (Priority: P2)

As a reader I no longer see the legacy "Weekly AI Analytics" preview on `/`; the same place links to
the new weekly page. As the operator, fetch runs stop writing weekly v2 observations and coverage.

**Independent Test**: after the change `/` has no `weekly-analytics-preview` section and has a link to
`/weekly`; a fetch cycle writes no `weekly_*` rows; `/weekly-ai-analytics` answers with a redirect.

**Acceptance Scenarios**:

1. **Given** the new weekly page has a ready week, **When** `/` loads, **Then** it shows the link, not
   the legacy preview.
2. **Given** a stored legacy report, **When** `GET /api/news/weekly-analytics` is called, **Then** it
   still returns it (read-only data, same fields).

---

### User Story 4 - Monthly view (Priority: P3)

As a reader I open `/monthly` and see a calendar month (UTC) with the same sections, compared with the
previous month when that month is comparable. First usable month: November 2026 (ready on 2026-12-01).

**Independent Test**: seed two months of daily snapshots; the month is ready only with
`month_min_complete_days` complete days and a previous month shows comparison only when ready.

---

### Edge Cases

- A week with a missing digest day: the day is not zero attention; it counts as incomplete (006 rule).
- A holiday or weekend week with few items: ready if enough days are complete, but the sections that
  need volume (risers, coolers) use 006 minimums and may be empty; the page says "quiet week".
- A source outage: no per-source health table exists after v2 is retired; the proxy is publisher breadth
  (distinct publishers in scope) of the week against the previous week.
- Entity merged or aliased by an operator after the week was stored: the next recompute (methodology
  unchanged) updates the week if the payload changes; stored weeks are not frozen against overrides,
  same as 006.
- Methodology or extraction version changes: stored weeks are rebuilt by `--recompute-all` at $0.
- Weeks before the first comparable day (2026-10-12): not shown ("history only").
- Page and API load while no week exists: 200 with an unavailable state.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST define a week as Monday 00:00 to Sunday 23:59 UTC of digest days, and a
  month as a calendar month UTC; only completed periods are computed.
- **FR-002**: A period MUST be built only from stored 006 data (daily snapshots, evidence, entities,
  digest scope); no provider call for numbers.
- **FR-003**: Sections: top stories, top entities by type group, new entities, risers and coolers,
  event-type mix with delta, coverage line.
- **FR-004**: Each item MUST carry counts (articles, publishers, days) and links to supporting
  articles (at most `links_max`), and the days it appeared on.
- **FR-005**: A period MUST have a status `unavailable`, `partial`, `building_history` or `ready`,
  decided by complete days, volume and comparability thresholds that are code constants recorded in
  the stored payload with a `METHODOLOGY_VERSION`.
- **FR-006**: Comparison sections MUST require the previous period to be `ready` and its publisher
  breadth within the stored ratio.
- **FR-007**: Periods MUST be stored once per (kind, start) with a payload hash; recompute writes only
  when the hash changes; `--recompute-all` rebuilds all periods at $0.
- **FR-008**: The brief (US2) MUST be a separate table keyed by input hash, validated mechanically
  like 007, under a per-brief and per-run dollar cap, off by default.
- **FR-009**: Pages and API MUST read stored data only and degrade to an unavailable state on a
  missing or unreadable row (never 500).
- **FR-010**: Weekly v2 code, settings, cron, workflows, tests and collection hooks MUST be removed
  as listed in `plan.md`; legacy report tables and the read API stay.
- **FR-011**: A new code doc `src/app/core/periodic/signals_period.md` MUST hold the intended
  behavior and be edited before the code.

### Key Entities

- **Period report**: one stored payload per (kind `week`|`month`, start date): status, methodology
  version, thresholds, coverage, payload hash, sections.
- **Period brief**: one brief per period, status `ok`/`invalid`, input hash, model, payload.

## Success Criteria

- **SC-001**: `/weekly` for each completed week since 2026-10-12 renders from stored data in one
  request without a provider call; 3 weeks are available by the first deploy (10-12, 10-19, 10-26).
- **SC-002**: Deterministic computation of one week takes under 5 s on prod data and costs $0.
- **SC-003**: Paid cost of the weekly brief is at most $0.05 per week by the ledger (expected about
  $0.01); monthly at most $0.08 (expected about $0.02); a run never exceeds `--max-usd`.
- **SC-004**: After cleanup, a fetch cycle writes zero `weekly_*` rows; database growth of about
  1.3 MB/day from observations stops; about 4,300 lines (code 2,350, tests 1,660, scripts and docs 230) are removed.
- **SC-005**: Each section's top items can be traced by a reader to day pages and articles.
