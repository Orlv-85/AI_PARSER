# Prompt (Codex fix round, gpt-6.1-sol high): spec 018 item 4b review findings (2026-11-02)

Same worktree and branch as your item 4b work:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job`. Do not commit,
push or use gh. No network, no paid calls. Do not spawn a doc review or any sub-agent.
Review report: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/tasks/item4b-daily-job.review-20261102-133836.md`.

Doc first (`src/app/core/bulletin/daily.md`), then a failing test, then the code. Fix exactly these:

1. Lock wait must outlast the world job. The world service (`ai-news-daily-world`, timer 04:00 UTC,
   `TimeoutStartSec=9600`) can hold the shared host lock until 06:40 UTC; the bulletin (04:30 UTC)
   now stops waiting at 06:00 and skips the day.
   - Rule: bulletin start + LOCK_WAIT >= world start + world TimeoutStartSec. Set
     `LOCK_WAIT=8100` in `scripts/run_daily_bulletin_job.sh` and bulletin `TimeoutStartSec=10100`
     in `scripts/install_daily_timers.sh` (lock wait + 1800 step + kill grace + cleanup, with margin).
   - Test: read both timer times, the world TimeoutStartSec and the bulletin LOCK_WAIT from the
     files (not hardcoded) and assert the rule.
   - Doc: replace the "decided 2026-11-02 (agent)" line on 5400 s with the rule and why; add one
     line: while `world_stream_in_bulletin` is off the world screening is not an input, so a
     skipped or cut world night does not change the bulletin.
2. Service budget test derives every term from the script: LOCK_WAIT, DAILY_LIMIT, every
   `timeout -k <grace> <limit>` in it (container removals before and after the step, kill grace),
   so changing the cleanup timeout 60 -> 600 fails the test (that mutation survived).
3. Failure log keeps the cause. In `bulletin_daily` (`src/app/cli/main.py`) the `except Exception`
   path logs through `log_event` with `event="bulletin_daily_failed"`, `date`, and
   `error=type(exc).__name__`, `detail=str(exc)[:200]`, plus the traceback (`exc_info`, if
   `log_event` or the JSON formatter supports it; check `app/observability/logging.py`, do not
   change the formatter). Regression test: an injected `OSError("journal directory read-only")`
   gives a log record with the date, `OSError` and the message, exit code 0.

Keep the copied `.env` parser as it is. Change nothing else.

Checks: while working run only `tests/unit/test_bulletin_daily.py tests/unit/test_daily_timers.py
tests/unit/test_deepseek_digest.py` and ruff. Once at the end: `make lint
PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`, full
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q`,
`python scripts/check_code_docs.py`, crapper on `src/app/cli/main.py src/app/core/bulletin/daily.py`
(no new function above 10), mutator with `--use-existing-coverage` on `src/app/core/bulletin/daily.py`
and a narrow `--test-command` (the bulletin daily tests). Report: what changed (file:line), each
check's result line, anything not run and why.
