Fixed all three findings:

- [run_daily_bulletin_job.sh:57](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job/scripts/run_daily_bulletin_job.sh:57): lock wait increased to **8100 seconds**.
- [install_daily_timers.sh:106](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job/scripts/install_daily_timers.sh:106): service timeout increased to **10100 seconds**.
- [test_daily_timers.py:65](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job/tests/unit/test_daily_timers.py:65): derives timer ordering and every timeout-budget term from the files.
- [main.py:516](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job/src/app/cli/main.py:516): structured failure log retains date, exception type and detail capped at 200 characters.
- [test_bulletin_daily.py:249](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job/tests/unit/test_bulletin_daily.py:249): verifies injected `OSError`, truncation and exit zero.
- [test_deepseek_digest.py:667](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job/tests/unit/test_deepseek_digest.py:667): updated lock-wait expectations.
- [daily.md:47](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job/src/app/core/bulletin/daily.md:47): updated rules and world-stream-off behavior.

TDD reproduced **5 expected failures** before implementation. The cleanup mutation `60 → 600` now fails the budget test (`10610 < 10100`); restoration passes.

| Check | Result | Exit |
|---|---|---:|
| Scoped tests | 106 passed | 0 |
| Ruff | All checks passed | 0 |
| `make lint` | Rated 10.00/10 | 0 |
| Full pytest | Passed; coverage run confirmed 1982 passed, 2 skipped | 0 |
| Code docs | 14 checked, ok | 0 |
| Crapper | Highest bulletin/daily complexity: 9 | 0 |
| Mutator | 12 sites: 11 killed, 0 survived, 1 uncovered | 0 |

The two PostgreSQL tests skipped because `AINEWS_TEST_POSTGRES_URL` is unset. Existing coverage excluded one default-argument mutation. Tracebacks remain unavailable because neither `log_event` nor the formatter supports them.

The copied `.env` parser and formatter are unchanged. No network, paid calls, commits, pushes or sub-agents used.