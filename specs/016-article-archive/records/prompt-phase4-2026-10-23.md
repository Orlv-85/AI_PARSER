# Prompt: spec 016 phase 4 - nightly archive job (2026-10-23)

You implement **phase 4 of spec 016** (tasks T010-T011) in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
Phase 3 is merged (PR #96, master `da30702`), not yet deployed; this PR and #96 ship together in one
tag. The coordinator is session `ai-parser-d4`; report to it by SendMessage when done. Do not ask the
owner design questions (AGENTS.md "Owner And Questions").

Production-sensitive: no change to the fetch/digest units or scripts, the lock path, ports,
retention, `scripts/db_maintenance.sh` or deploy workflows.

## Read first

1. `AGENTS.md`.
2. `specs/016-article-archive/tasks.md` (Phase 4), `plan.md` "Daily capture (A3)".
3. `scripts/run_daily_fetch_job.sh`, `scripts/run_daily_digest_job.sh` (image from
   `.last_deploy_image`, lock, named container, timeout handling), `scripts/install_daily_timers.sh`,
   `scripts/deploy_prod.sh` (it runs the installer, line ~275).
4. Tests of those scripts: `tests/unit/test_deepseek_digest.py` (job script tests),
   `tests/unit/test_daily_timers.py`.
5. `src/app/core/archive/capture.md`.

## Rules fixed by the coordinator

- `scripts/run_daily_archive_job.sh`: `APP_IMAGE` from `.last_deploy_image` exactly like the other
  jobs (without it compose uses a stale local `:latest`); `flock -w 1800` on
  `/tmp/ai-news-auto-update.lock`; `timeout -k 30 1680` around
  `docker compose ... run --rm --name ai-news-archive app ai-news archive capture --max-seconds 1500`;
  remove the named container on timeout; always exit 0, one stderr line on failure (lock timeout,
  capture failure, timeout).
- `install_daily_timers.sh` adds `archive` at 03:00 UTC with `TimeoutStartSec=3600` and log
  `logs/daily-archive.log`; fetch and digest units stay byte-identical (assert it in the test).
- Code doc Behavior gets the schedule rule with its tests; `covers` gets the script glob.
- `docs/deploy.md` "Article archive": where the log is and how to read `archive_capture_finished`.

## Steps

1. Worktree: `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch` then
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add ../AI_PARSER-wt-016-p4 -b feat/016-archive-nightly-20261023 origin/master`.
   Remove the p3 worktree. Checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/<tool>`.
2. Doc first, then the script, the installer, tests named as in tasks.md T011
   (`test_archive_job_script_is_isolated` in `tests/unit/test_deepseek_digest.py`,
   `test_install_timers_includes_archive` in `tests/unit/test_daily_timers.py`); the isolation test
   covers: image from `.last_deploy_image`, lock wait, timeout kill + container removal, exit 0 on
   failure.
3. Checks: `bash -n scripts/*.sh`; scoped tests; full gate:
   `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
4. Commit `feat(archive): nightly archive capture job at 03:00 UTC (016 phase 4)` with your
   harness's Co-Authored-By line; push; `gh pr create --base master --title "feat(archive): nightly archive capture job (016 phase 4)" --body "<summary, checks, decisions, what to check on prod after the first night>"`.
   Do not merge, do not tag, no prod access.

## Out of scope

Phase 5 admin stats; nightly-health changes; user agent; downloader timeouts as outage.

## Report to the coordinator (SendMessage to `ai-parser-d4`)

PR link and head SHA; files changed; tests added; full gate summary; decisions not fixed here, one
line each; doubts.
