1. **P1 — Schedule can miss the bulletin entirely.** [run_daily_bulletin_job.sh:57](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job/scripts/run_daily_bulletin_job.sh:57): bulletin stops waiting at 06:00, but world’s allowed steps, grace and cleanup can hold the lock until 06:06:20 even without initial contention. Bulletin then exits successfully without building. If world instead times out waiting for digest, bulletin can run without completed world screening. **Fix:** coordinate prerequisite completion and budget the whole sequence through bulletin completion by 06:00; test delayed predecessors.

2. **P2 — Operational failures lose their diagnostic details.** [main.py:515](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job/src/app/cli/main.py:515): injecting `OSError("journal directory read-only")` produces only `{"…","message":"bulletin_daily_failed"}`. `JsonFormatter` drops both `extra.date` and exception information; exit zero and the generic summary leave the cause invisible. **Fix:** emit structured date, stage and exception type through `log_event`, with a regression assertion.

Mutation results, executed without modifying repository files:

| Mutation | Result / detecting test |
|---|---|
| Missing DS key wrongly stores skipped | Killed — `test_daily_without_ds_key_stores_title_only` |
| Remove daily commit | Killed — `test_daily_assesses_builds_writes_and_stores` |
| Skip configured writer | Killed — `test_daily_assesses_builds_writes_and_stores` |
| Script exits nonzero | Killed — off/default and failure-isolation tests |
| Lock wait becomes 1800 | Killed — job-run and timer tests |
| Timer becomes 04:00 | Killed — `test_bulletin_timer_runs_after_the_world_job` |
| Cleanup timeout becomes 600 | **Survived all bulletin script/timer tests** |

The current service margin is real: **7500 − 7370 = 130 seconds**. However, its test hardcodes cleanup/grace values; the surviving mutation exceeds the service budget. Derive those values from the script.

Other review conclusions:

- The prompt’s provider-failure premise is incorrect: DeepSeek errors/caps/timeouts preserve and store titles; Jev request failures still reach build. Setup exceptions abort as `daily.md` specifies. Assessment commits survive; pending bulletin writes roll back on session closure. Keeping unexpected faults separate from expected provider fallback is reasonable.
- Build/assess outputs, storage, dry runs and exit codes remain compatible normally. Differences: assessed/writer logs now serialize fields; assessed logging occurs before source loading; phrases load even without a digest; assess dry-run now calls `get_settings`; skipped `--write` evaluates the clock before its no-op helper.
- Daily reruns reuse capped journals. Jev’s pre-existing per-date/per-cap journals are not a global calendar-day spending cap.
- Sudoers matches installer commands exactly. Both settings default off and have no consumers. Doc registrations/name checks pass. **Keep the copied `.env` parser for this change**, avoiding unrelated world-job changes.

Validation: requested suite **172 passed**; writer/assessment/sudoers checks **88 passed**; code-doc check **14 checked, OK**. Full repository checks were outside this review’s scope. **Not clean for merge.**