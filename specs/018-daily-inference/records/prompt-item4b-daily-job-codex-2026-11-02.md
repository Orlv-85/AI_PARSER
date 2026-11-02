# Prompt (Codex, gpt-6.1-sol high): spec 018 item 4b, bulletin daily job and switches (2026-11-02)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`feat/018-item4b-daily-job`, checked out from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job`. Do not touch any
other directory. Do not run git commit, push or any gh command. No network, no paid calls (tests
use fakes; never call Jev or DeepSeek). Do not spawn a doc review or any sub-agent: a separate
reviewer (another model) reviews the code and the doc after you.

Speed rule: while working run only the feature's tests and `ruff` on changed files; at the end run
the full suite, `make lint`, crapper and mutator once each, in that order; after a fix rerun only
the check that failed.

## Scope

Item 4 of spec 018: 4a (merged, PR #204: table `bulletins`, `BulletinRepo`, `bulletin build`
stores, `GET /api/news/bulletin`); 4b (this one): the daily job and the switches (FR-019, FR-020);
4c later: the hidden preview page. Spec: `specs/018-daily-inference/spec.md` FR-012, FR-019,
FR-020, SC-001.

## Decisions already made (put them in the doc's Decisions as "decided 2026-11-02 (agent)")

- One CLI command does the day: `ai-news bulletin daily [--date D]` (default D = yesterday UTC):
  1) `bulletin assess` logic for D (Jev, its existing cap `ASSESS_DEFAULT_MAX_USD`; skip answered);
  2) build; 3) the writer (DeepSeek, `WRITER_MAX_USD_PER_DAY`) when `DS_API_KEY` is set, else
  title-only with a logged reason; 4) store through `BulletinRepo` (ready or skipped; a posted day
  is never replaced). Reuse the existing functions of `bulletin assess` / `bulletin build`; do not
  copy their bodies (extract small shared helpers if needed). One JSON summary line on stdout
  (`date`, `status`, `reason`, assess summary, writer summary, `stored`/`refused`). Exit 0 when a
  day was stored or legitimately skipped; non-zero only on a usage error.
- Missing `JEV_API_KEY`: skip the assess step with a logged reason and build from the answers already
  stored (a day without answers is stored as skipped `no_assessments`, as the builder already does).
- Job script `scripts/run_daily_bulletin_job.sh`, copied in shape from `scripts/run_daily_world_job.sh`
  (env from environment or `.env`, `APP_IMAGE` from `.last_deploy_image`, same host lock file with
  `flock -w`, per-step `timeout`, always exit 0, docker compose run of the app image with the CLI).
  Off unless `AINEWS_BULLETIN_JOB_ENABLED` is true (paid calls; the owner turns it on).
- Timer at 04:30 UTC (not 04:00): the world job starts at 04:00 and holds the host lock about 26
  minutes (first night), worst case about 2 h; the bulletin must run after it, because with the
  world switch on it needs the world answers of D. Lock wait 5400 s so the job still starts by
  06:00 UTC (SC-001). Add the service and timer to `scripts/install_daily_timers.sh` like the world
  job (service `TimeoutStartSec` covering lock wait plus step limits, checked by a test as for the
  world job).
- Settings (FR-019), both default off, in `src/app/config/settings.py` like
  `world_stream_in_bulletin`: `bulletin_home_page` (env `AINEWS_BULLETIN_HOME_PAGE`) and
  `bulletin_post_channels` (env `AINEWS_BULLETIN_POST_CHANNELS`). In 4b they are only defined,
  documented and tested for defaults; nothing reads them yet (item 6 and item 8 will). Also
  `AINEWS_BULLETIN_JOB_ENABLED` is read by the script only. Document all three in
  `docs/configuration.md` (one line each, operator facts only).

## Steps (doc first, then failing tests, then code)

1. Read `AGENTS.md`, `src/app/storage/bulletin_store.md`, `src/app/core/bulletin/builder.md`,
   `writer.md`, `world_change.md`, `src/app/core/world/world.md` (the world job part and its tests of
   the script and timers), `scripts/run_daily_world_job.sh`, `scripts/install_daily_timers.sh`,
   `src/app/cli/main.py` (`bulletin assess`, `bulletin build`), `src/app/config/settings.py`, and the
   tests that check the world job script and timer (find them with `rg -l run_daily_world_job tests`).
2. Feature doc `src/app/core/bulletin/daily.md` (module `src/app/core/bulletin/daily.py`; covers
   `src/app/core/bulletin/daily.py` and `scripts/run_daily_bulletin_job.sh`): Behavior (Mermaid
   flow; each rule names its tests), Decisions, Invariants, Code map, Tests. Register it in
   `docs/README.md`, `README.md`, `src/app/README.md`. If `install_daily_timers.sh` is covered by
   another doc, add the bulletin timer there in one line pointing to `daily.md`.
3. Failing tests (new `tests/unit/test_bulletin_daily.py`; script/timer tests next to the world
   job's), run and see them fail:
   - `test_daily_assesses_builds_writes_and_stores` (fake Jev and writer; one ready row)
   - `test_daily_without_ds_key_stores_title_only`
   - `test_daily_without_jev_key_builds_from_stored_answers`
   - `test_daily_skipped_day_is_stored`
   - `test_daily_posted_day_is_refused_and_exits_zero`
   - `test_daily_defaults_to_yesterday_utc`
   - `test_daily_prints_one_summary_line`
   - `test_bulletin_switches_default_off`
   - `test_bulletin_job_off_by_default` (script exits 0 and does nothing without the switch)
   - `test_bulletin_timer_runs_after_the_world_job` (04:30 UTC, same lock, lock wait 5400)
   - `test_bulletin_service_timeout_covers_lock_wait_and_steps`
   Follow how the world job's script tests run the script (fake docker / PATH stubs).
4. Code, smallest change in the current style; functions small (complexity under 10).
5. Final checks (once each, in this order; report last lines and exit codes):
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`
   - `PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -5`
   - `bash -n scripts/run_daily_bulletin_job.sh scripts/install_daily_timers.sh && sh -n scripts/run_daily_bulletin_job.sh`
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/crapper/crapper src/app/core/bulletin/daily.py src/app/cli/main.py`
     (report functions of `daily.py` and the bulletin commands with CRAP >= 10)
   - `~/tools/unclebob/dryer/dryer --threshold 0.8 src/app/core/bulletin/daily.py src/app/cli/main.py`
     (report pairs that involve code you wrote)
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_bulletin_daily.py" src/app/core/bulletin/daily.py`
     (kill survivors with tests or give a one-line reason)
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py --diff origin/master --strict; echo exit=$?` (alone, last)

## Report (your final message)

Files changed, one line each; failing-test output of step 3; outputs of step 5; mutator sites,
killed, survived, uncovered and what you did with survivors; anything you decided yourself or
could not do, one line each.
