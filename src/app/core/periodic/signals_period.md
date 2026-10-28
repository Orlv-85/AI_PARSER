<!-- code-doc
module: src/app/core/periodic/signals_period.py
covers:
  - src/app/core/periodic/*.py
  - src/app/storage/period_signals*.py
  - src/app/storage/migrations/versions/*period_signal*.py
  - src/app/web/routes/period.py
-->
# Period AI Signals

Weekly (and later monthly) view of the AI signals: sums and comparisons of the stored daily data
(`core/daily/signals.md`) over a completed period. Everything is deterministic and costs $0; no
provider is involved. Shipped: the pure rules (bounds, thresholds, status, compute), storage, the
command `ai-news period-signals`, the nightly step and the read API, all behind
`AINEWS_PERIOD_SIGNALS_ENABLED` (default off). The page and the paid brief come in later releases.

This file is the intended current behavior of 017. `specs/017-weekly-monthly-signals/` is the process
and history.

## Behavior

```mermaid
flowchart LR
  daily["Stored daily snapshots, coverage, evidence of the period days"] --> input["PeriodInput"]
  prev["Previous period of the same kind: status, publishers, event stories"] --> input
  input --> cov["Coverage line"]
  cov --> status["Status: unavailable, partial, building_history, ready"]
  input --> cmp["Comparison: none, suppressed or ready"]
  input --> sums["Top stories, top entities, New, event mix"]
  cmp --> trend["Risers and coolers: Sunday snapshot or shared helper"]
  status --> payload["Payload + payload_hash"]
  sums --> payload
  trend --> payload
```

The numbers live in the code: fields of `PeriodThresholds` (by kind) in `period_model.py`; the daily
`Thresholds` still decide what a complete day is and what Rising means.

**Periods**
- Week: Monday to Sunday of digest days D (UTC); key is the Monday. Month: calendar month UTC; key is
  the first day. Only completed periods are computed. Tests: `test_week_runs_monday_to_sunday`,
  `test_week_across_a_year_change`, `test_month_lengths`, `test_previous_month_crosses_the_year`.
- Thresholds per kind (`PeriodThresholds.for_kind`): `min_complete_days`, `min_items`,
  `breadth_ratio`, `quiet_items`, and the caps and minimums of the lists below. Tests:
  `test_thresholds_by_kind`.

**Status** (first rule that holds wins)
- `unavailable`: no day of the period has a usable snapshot.
- `partial`: fewer than `min_complete_days` complete days, or fewer than `min_items` items.
- `building_history`: numbers are fine but there is no usable previous period (its status is
  `ready` or `building_history`), so nothing is compared.
- `ready`.
- A day is complete by the daily rule (`DayCoverage.complete` at the daily `complete_ratio`) and
  belongs to the comparable range. A day without a coverage row is missing: it is listed in
  `missing_days` and counted neither as complete nor as a zero day. Tests:
  `test_period_status_precedence`, `test_a_missing_day_is_not_zero`,
  `test_status_unavailable_partial_building_history_ready`,
  `test_coverage_missing_day_is_listed_not_zero`.

**Coverage line**
- Days complete of days in the period, items, extracted share, distinct publishers, and `quiet`
  when items are below `quiet_items` (sections still show; the opening line says "quiet"). Tests:
  `test_coverage_line_counts_days_items_and_publishers`,
  `test_coverage_incomplete_day_is_not_complete_and_quiet_flag`.

**Sections**
- Top stories: the daily `top_stories` of all days, merged by event type plus entity set (a story
  without entities merges by label); ranked by distinct publishers, then days, then articles; at
  most `top_max`. Publishers are the larger of the best daily count and the distinct publishers
  among the stored links (a lower bound: the snapshot keeps at most a few links per story).
  Tests: `test_top_stories_merge_across_days_by_event_type_and_entities`,
  `test_top_stories_rank_by_publishers_then_days_and_cap`.
- Top entities: for models, products, companies and technologies, ranked by distinct articles, then
  publishers, from the mentions of the period articles; entities that need review are skipped; at
  least `top_entity_min_articles` articles and `top_entity_min_publishers` publishers; at most
  `top_entity_max` per group; each with its days and links. Tests: `test_top_entities_by_group_with_minimums`.
- New this period: the union of the daily `new` lists, confirmed first, then by first-seen day,
  then publishers; an entity seen first as early and later as confirmed is shown confirmed with its
  first day; at most `new_period_max`. Tests: `test_new_union_confirmed_first_with_first_seen_day`,
  `test_new_union_is_capped`.
- Event mix: stories and articles per hard event type, summed from the daily chips; other types as
  "+N more"; the delta in stories against the previous period only when the comparison is `ready`.
  Tests: `test_event_mix_sums_chips_with_delta_and_more`.
- Risers and coolers (week): the daily computation with D = the Sunday. The Sunday snapshot is used
  when its `methodology_version` is the current daily one and its Rising was usable; otherwise the
  shared helper runs over the week bounds (`trend_windows`, `trend_delta`). Shown only when the
  comparison is `ready`. Month: not built here (`not_built`). Tests:
  `test_rising_equals_the_sunday_snapshot`,
  `test_rising_from_the_helper_matches_the_sunday_snapshot_when_methodology_is_old`,
  `test_rising_snapshot_without_usable_windows_falls_back_to_the_helper`, `test_month_has_no_risers_yet`.

**Comparison and publisher breadth**
- `none` without a usable previous period; `suppressed` with reason `low_publisher_coverage` when
  the publishers of this period divided by those of the previous one are below `breadth_ratio`
  (a source outage looks like a drop in topics, not a trend); otherwise `ready`. Suppression hides
  the event deltas and the risers and coolers; the status stays `ready`. Tests:
  `test_low_publisher_coverage_suppresses_the_comparison`,
  `test_no_comparison_without_a_usable_previous_period`.

**Payload and hash**
- The payload carries `PERIOD_METHODOLOGY_VERSION`, the daily methodology version, the extraction
  version and the thresholds. `payload_hash` is the daily one (ignores `generated_at`); the same
  input gives the same hash and the order of days, articles and coverage rows does not matter.
  Tests: `test_payload_hash_is_stable_and_ignores_day_order`,
  `test_payload_is_json_and_records_versions_and_thresholds`.

**Storage**
- Two tables, no foreign keys: `period_signal_reports` (one row per `period_kind` and `period_start`:
  end, status, versions, `payload_hash`, thresholds, payload, coverage JSON) and
  `period_signal_briefs` (created empty; filled by the brief release). Tests:
  `test_upgrade_matches_models_and_downgrade_drops_only_period_tables`,
  `test_upgrade_after_create_all_keeps_existing_tables`, `test_single_head_and_chain`.
- A period is stored only when its `payload_hash` differs from the stored one; the second run
  writes nothing. Tests: `test_second_run_writes_nothing`, `test_changed_input_rewrites_only_that_period`.
- The input of a period is its days plus the 7 days before it (the helper path needs 14 days), the
  stored daily snapshots, per-day coverage, the evidence (reconciled in memory, nothing persisted)
  and the stored previous period (status, publishers, event stories). An unreadable previous row
  counts as no previous period; an unreadable daily snapshot counts as no snapshot. Tests:
  `test_run_round_trip_stores_oldest_first_and_links_the_previous_week`,
  `test_unreadable_stored_previous_period_counts_as_none`.

**Run** (`ai-news period-signals [--kind week|month] [--period YYYY-MM-DD] [--backfill N] [--recompute-all]`)
- With `AINEWS_PERIOD_SIGNALS_ENABLED` off the command prints `{"state": "disabled"}`, exits 0 and
  writes nothing. Tests: `test_flag_off_says_so_and_writes_nothing`,
  `test_month_and_flag_off_do_nothing`.
- Default: the latest completed week (the week whose Sunday is before today, UTC). `--backfill N`
  takes N weeks ending at the target, `--period` names any day of the target week, and
  `--recompute-all` takes every week from the first one; periods run oldest first so each reads the
  stored previous one. Tests: `test_targets_default_backfill_and_clipping_before_the_first_week`,
  `test_backfill_period_and_recompute_all`, `test_default_run_computes_the_latest_completed_week`.
- The first computable week is the first full Monday-Sunday week inside the comparable range
  (`first_week`); earlier weeks are dropped from a backfill and reported as `skipped_before_first`;
  an uncompleted or earlier `--period` is refused (exit 2). Tests: `test_first_and_latest_week_bounds`,
  `test_uncompleted_or_early_period_is_refused`, `test_bad_arguments_exit_2`.
- `--kind month` reports `{"state": "not_built"}` and writes nothing until the monthly release.
  Tests: `test_month_is_reported_not_built_and_writes_nothing`.
- The nightly step in `scripts/run_daily_digest_job.sh` runs the default command after the daily
  signals with a time-budget guard; its failure never changes the job result. Tests: none (shell;
  checked by `bash -n`).

**API** (stored data only; `brief` is always null for now)
- `GET /api/news/period-signals?kind=week&start=YYYY-MM-DD`; without `start` the newest `ready` or
  `building_history` period, else the newest stored one. A missing row or an unreadable payload gives
  200 with status `unavailable`, never 500. Tests: `test_ready_week`,
  `test_partial_week_is_served_with_its_status`, `test_default_is_the_latest_ready_or_building_period`,
  `test_default_falls_back_to_a_partial_week`, `test_missing_row_is_unavailable_200`,
  `test_corrupt_row_is_unavailable_200`, `test_invalid_query_is_422`.
- `GET /api/news/period-signals/index[?kind=]`: stored periods newest first (kind, start, end,
  status, computed time); no payload is read. Both routes are public like the daily one. Tests:
  `test_index_lists_newest_first_without_payloads`, `test_empty_index`,
  `test_auth_middleware_coverage_is_pinned`.
- No provider code is imported on the request path. Tests: `test_request_path_does_not_import_provider_code`.

## Decisions

| Decision | Why |
| --- | --- |
| Weeks are Monday-Sunday UTC of digest days; months are calendar UTC (decided 2026-10-28, planner) | the unit of the daily signals is the digest day; matches the old Monday report |
| Completed periods only (owner answer Q3) | "week so far" invites noisy partial numbers; the daily block covers current days |
| Built from daily snapshots and evidence, not raw articles (decided 2026-10-28, planner) | snapshots and evidence survive article retention; event types come from the chips |
| One definition of "rising": the daily one at the Sunday (decided 2026-10-28, planner) | no second method on the site |
| Coverage = digest-day completeness plus publisher breadth, no per-source slot table (decided 2026-10-28, planner) | judged on what the reader sees; breadth is the proxy for source outages |
| New package `core/periodic/` and `period_` names (decided 2026-10-28, planner) | the feature reads daily data and is not daily |
| Deterministic numbers ship before the brief (decided 2026-10-28, planner) | the paid step has its own flag and release |
| The daily Rising window ending on D includes D (verified 2026-10-28, agent): `trend_windows` in `core/daily/signals_trend.py` takes `day - i` for `i` in `range(w)` (line 61, the same line was in `signals_compute.py` before the move), and the previous window is `range(w, 2 * w)` (line 62) | the Sunday snapshot is exactly the week against the week before, so the weekly risers reuse it |
| The shared Rising/Cooling rule lives in `core/daily/signals_trend.py`, not in `core/periodic/` (decided 2026-10-28, agent) | 006 code imports it without importing the period package; payload hashes of the 006 fixtures are unchanged, so no `METHODOLOGY_VERSION` bump |
| The helper path does not exclude the Sunday's New entities from risers (decided 2026-10-28, agent) | the New list of D is not an input of the period; the fixture week shows the same list as the snapshot |
| A previous period counts as usable when `ready` or `building_history` (decided 2026-10-28, agent) | otherwise the second week would also wait: the first week is never `ready` (it has no previous) |
| Comparison is hidden (event deltas, risers, coolers) when breadth is low, status stays `ready` (decided 2026-10-28, agent) | the numbers of the period are fine; only the comparison is unreliable |
| Distinct publishers of a merged story are a lower bound from stored links (decided 2026-10-28, agent) | the snapshot stores a few links per story, not all publishers; re-clustering days is not worth the risk |
| Values of the list caps and minimums, not given in the plan (decided 2026-10-28, agent): week top 8, entities 5 per group with 3 articles and 2 publishers, New 10; month 12, 8, 6 and 3, 16 | first guess near the daily scale; changing them is a methodology bump |
| The first computable week is the first full week inside the comparable range, not the week that contains the comparable-from date (decided 2026-10-28, agent) | the plan says weeks before 2026-10-12 are never computed; a partial first week would be `partial` anyway |
| Month kind is reported `not_built` with exit 0, not refused (decided 2026-10-28, agent) | the nightly command and an operator can pass it without a failure; the monthly release replaces it |
| The default API read prefers the newest `ready` or `building_history` period over a newer `partial` one (decided 2026-10-28, agent) | a reader should see numbers that can be trusted; a partial week is still served by `start` or when nothing else exists |
| The run reconciles evidence in memory and reads entity ids from `ai_entities`; it does not persist reconciliation (decided 2026-10-28, agent) | the period run writes only its own tables; an entity not yet stored has id 0 until the daily run stores it |
| A period run is a function in `period_run.py`, the command only parses options (decided 2026-10-28, agent) | testable without the CLI, same split as the daily run |
| Month risers and month-only rules are not built here (R6) | bounds and thresholds for months exist; the monthly view ships last |

## Invariants

- Pure: no database, no clock, no provider import, $0. `generated_at` is an input. Tests:
  `test_payload_hash_is_stable_and_ignores_day_order`.
- A missing day is never a zero day. Tests: `test_a_missing_day_is_not_zero`,
  `test_coverage_missing_day_is_listed_not_zero`.
- A period run writes only `period_signal_*` tables; digest, articles, signals and weekly tables stay
  untouched. Tests: `test_a_period_run_writes_only_period_signal_tables`.
- The daily snapshot payload hashes do not change by the extraction of the shared helper. Checked
  once when it moved (before and after table in the PR); the daily tests remain the guard
  (`test_rising_and_cooling_with_usable_windows`, `test_windows_need_six_complete_days_and_comparable_range`).

# Code map

| File | Role | Pure |
| --- | --- | --- |
| `signals_period.py` | Public entry: re-exports `compute_period`, `PeriodInput`, `PeriodThresholds`, `payload_hash` | yes |
| `period_model.py` | Bounds (`period_bounds`, `period_days`, `previous_start`), `PeriodThresholds`, `PeriodInput`, `PreviousPeriod`, `period_status` | yes |
| `period_compute.py` | `compute_period` and one function per section; `PERIOD_METHODOLOGY_VERSION` | yes |
| `period_run.py` | `run_periods`, `target_weeks`, `first_week`, `latest_completed_week`: pick periods, compute, store | no |
| `storage/period_signals.py` | `PeriodSignalRepo`: `context`, `load_input`, `previous`, `save_report`, `get_report`, `latest`, `index` | no |
| `storage/migrations/versions/f4a9c1d27b83_add_period_signals.py` | the two tables, skip-if-exists, `down_revision` `e7b4c2a9d150` | no |
| `web/routes/period.py` | the two read routes; response models `PeriodSignalsResponse`, `PeriodSignalsIndexResponse` in `web/models.py` | no |
| `cli/main.py` `period-signals` | options and flag check; flag `period_signals_enabled` in `config/settings.py` | no |
| `core/daily/signals_trend.py` | Shared Rising/Cooling rule: `trend_windows`, `trend_delta`, `TrendRow` | yes |

Flow: `compute_period` -> `coverage_line`, `period_status`, `comparison`, then `top_stories`,
`top_entities`, `new_this_period`, `risers_and_coolers`, `event_mix`.

| Change | Place | Also |
| --- | --- | --- |
| Thresholds, caps, minimums | `PeriodThresholds.for_kind` | bump `PERIOD_METHODOLOGY_VERSION` |
| A section rule | `period_compute.py` | bump `PERIOD_METHODOLOGY_VERSION` |
| What Rising means | `signals_trend.py` and daily `Thresholds` | bump the daily `METHODOLOGY_VERSION` and the period one |

Not built yet: the page (R3), the brief and its flag and version row (R4), the month kind (R6). The
`period_signal_briefs` table exists and is empty.

Operator commands, enabling and rollback: `docs/period-signals.md`. `docker-compose.prod.yml` passes
`AINEWS_PERIOD_SIGNALS_ENABLED` from the server `.env` with default `false`, so the nightly step is a
no-op until the operator sets it (decided 2026-10-28 (coordinator): same path as the daily flag).

## Tests

Per rule: see Behavior. Files: `tests/unit/test_period_model.py`, `tests/unit/test_period_compute.py`,
`tests/unit/test_period_signals_repo.py`, `tests/unit/test_period_signals_migration.py`,
`tests/unit/test_cli_period_signals.py`, `tests/unit/test_web_period_signals_api.py`; fixture weeks
are built by `tests/unit/period_fixtures.py` from `tests/fixtures/daily_signals/` (the previous week is
the same days shifted back, thinned) and database weeks by `tests/unit/period_db.py`. No test calls
a provider.
