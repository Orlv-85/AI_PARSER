# Report: spec 018 item 5, W7 nightly job and report (2026-11-01)

Implementer report (background agent, model sonnet), saved by the coordinator. PR #193, branch
`feat/018-world-w7-job`, rebased on 34cfba7. No paid calls.

## Files

`scripts/run_daily_world_job.sh`, `scripts/install_daily_timers.sh`, `src/app/core/world_report.py`
(new), `src/app/cli/main.py` (`world report`), `src/app/storage/archive.py`; docs `world.md`,
`capture.md`, `docs/deploy.md`, `docs/configuration.md`, `docs/cli.md`; tests
`test_world_report.py` (new), `test_deepseek_digest.py`, `test_daily_timers.py`,
`test_archive_capture.py`, `test_world_text.py`, `test_world_storage.py`.

## Checks (implementer)

`make lint` clean; full pytest 1825 passed, 1 skipped; `check_code_docs.py --strict` exit 0;
`bash -n` clean; dryer none; crapper >= 10 only in untouched `period_signals` (16), `daily_publish`
(10). Mutation B7 now killed by `test_world_text_downloads_only_pending_documents`.

## Nightly job

D-1 under one host lock: `world collect`, `world screen`, `world texts`, `world screen`. Each step
its own container and timeout; always exit 0; a failed step logs and the next go on. Screen steps
skip without `JEV_API_KEY` (env or host `.env`). Money unchanged (one $0.10 per UTC day journal, no
`--max-usd`). `TimeoutStartSec` 5400 -> 9600 (test: lock wait + step limits + kill grace + removals
below it).

| Step | Limit | Basis |
| --- | --- | --- |
| collect | 2400 s | about 4 min a day; first night with D-2 catch-up about 10 min; bad-day retries |
| screen | 2700 s | 1,842 sequential requests, estimated 0.5-1.5 s each (no gate timing); leftovers stay `new` |
| texts | 900 s | up to 100 pages, 4 at a time, 1 s per host |
| screen 2 | 900 s | up to 100 requests with text |

Worst case about 9,060 s with the 1,800 s lock wait; normal night ends about 05:00 UTC.

## Switch on in production (estimate)

About 820 MB GDELT download (plus D-2 if incomplete); about 1,842 title requests ($0.034
measured); about 100 step-B requests ($0.007-0.018 estimated); up to 100 pages fetched; about
25-65 min.

## Deploy

The job script runs from the host checkout; deploy does `git checkout --force <tag>` then
`install_daily_timers.sh`, so one deploy updates script and unit. Timer enabled on every deploy;
job off until the switch is set.

## Report command

`ai-news world report --date D`: read-only; window D-1 and D; counts by state, `no_text` reasons,
`world_change` counts; cost from the world journals of D and D+1; top 20 assessed stories.

## Decided by the implementer

- `archive status` excludes world documents from `states` and `top_hosts_without_text`; `versions`
  and `archive_bytes` still count them (`test_archive_status_skips_world_documents`).
- Report cost shows journals of D and D+1.
- One lock for all four steps (texts share the archive cache); the lock may be held up to about
  1h55m in the worst case.
