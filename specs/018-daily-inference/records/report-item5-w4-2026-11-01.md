# Report: spec 018 item 5, W3 follow-ups and W4 collect job (2026-11-01)

Implementer: background agent (Sonnet), prompt `prompt-item5-w4-2026-11-01.md`; interrupted twice
by laptop sleep and once by a usage limit, resumed each time. Saved by the coordinator from the
agent's final message.

## Results

- Part 1: commit `ef286a1` on `feat/018-world-w3-storage` (PR #164); PR body updated.
- Part 2: PR #166 (`feat/018-world-w4-collect`), stacked on #164, must merge after it.

## Part 1 files

- `world.md`: invariants single writer and `core/world` never imports `app.storage`; rules for cuts,
  batching, prune boundary, unknown state; PostgreSQL checked manually 2026-11-01.
- `storage/world.py`: `transition` raises `InvalidTransition` for an unknown stored state.
- `tests/unit/test_world_storage.py`: relative-import resolution; tests
  `test_import_scan_resolves_relative_imports`, `test_world_core_never_imports_storage`,
  `test_world_candidate_cuts_long_url_title_and_error`, `test_world_upsert_batches_over_hash_chunk`,
  `test_world_upsert_empty_batch`, `test_world_prune_cutoff_boundary`,
  `test_world_transition_unknown_stored_state_is_invalid`.
- Mutation check: a lazy `from ...storage import world` in `core/world/filter.py` made
  `test_world_core_never_imports_storage` fail; reverted.

## Part 2 files

- New: `src/app/core/world_collect.py`, `scripts/run_daily_world_job.sh`,
  `tests/unit/test_world_collect.py` (10 tests).
- Changed: `core/world/gdelt.py` (`scan_file`, `FileResult` split from `scan_day`; W2 tests
  unchanged), `cli/main.py` (`world collect`), `scripts/install_daily_timers.sh` (unit and timer
  `ai-news-daily-world` 04:00 UTC, `TimeoutStartSec=5400`), `world.md`, `docs/deploy.md`,
  `docs/configuration.md`, `docs/cli.md`, `tests/unit/test_deepseek_digest.py` (job script tests),
  `tests/unit/test_daily_timers.py` (`test_install_timers_includes_world`, systemctl order),
  `tests/unit/test_world_storage.py` (allows `world_collect.py`).

## Checks (agent)

- Part 1: ruff, `make lint` (pylint 10.00), full pytest 1511 passed 1 skipped, code docs ok.
- Part 2: ruff, `make lint`, full pytest 1528 passed 1 skipped, code docs 10 ok, `bash -n` ok,
  scoped world and timer tests 79 passed, dryer no duplicates, crapper max 9 (two helpers extracted
  from `collect_day`, which scored 11).

## PostgreSQL (manual, throwaway DB in `ainews-pg-test`, dropped)

upgrade head / downgrade -1 / upgrade head ok; upsert 1200 + 1 duplicate -> (1200, 1), again ->
(0, 1200); `record_file` done then missing -> `done_files` file then empty; prune (1, 0) for a
31-day row; transition to `failed` ok. Collect not run on PostgreSQL.

## Smoke (real GDELT, temp SQLite, deleted)

`world collect --date 2026-10-30 --max-files 3`: files 3, rows 3388, matched 50, kept 39, new 39,
repeats 0, missing 0, partial false. Second run skipped all 3 files, no new rows.

## Deploy

`scripts/deploy_prod.sh` runs `install_daily_timers.sh` on every deploy when
`AINEWS_DAILY_SCHEDULER=systemd`, so the timer is enabled on deploy; with the switch off the 04:00
run logs `world collect skipped: AINEWS_WORLD_COLLECT_ENABLED is off` and exits 0.

## Decided by the agent

- Switch named `AINEWS_WORLD_COLLECT_ENABLED` (repo prefix); read from env or host `.env` by the
  job script; no compose or Settings change.
- Orchestration in `core/world_collect.py`, outside `core/world/`, because `storage/world.py`
  imports `core/world/gdelt.py`.
- Job processes only yesterday; a day cut short by timeout is finished by hand with
  `ai-news world collect --date D`.
- Job timeout 3300 s, unit limit 5400 s, no `--max-seconds`; a timeout kill loses the summary line
  but at most one file of data.
- Stop rule as W2: 12 missing files in a row stop the run; unread files count as missing, not
  recorded.
- No `--dry-run` for collect.

## Questions for the owner

None about readers or money. Turning on `AINEWS_WORLD_COLLECT_ENABLED` in production (~820 MB/day)
is a separate owner decision.
