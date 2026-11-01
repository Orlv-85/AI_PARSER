# Review: PR #193, spec 018 item 5 W7 (2026-11-01)

Reviewer: background agent (model sonnet), read-only. Saved by the coordinator.

## Verdict: merge (no must-fix)

- Switch off (default, production now): exit 0 after the env/`.env` parse and one line; no lock,
  docker, download or key read beyond a non-empty test. Key never echoed, not in docker args.
- Host lock users: fetch and digest (7200 s wait), archive (1800 s), auto-update cron (`flock -n`,
  01:00). With the switch on the world run holds the lock from about 04:00 UTC for 25-65 min,
  about 1h55m worst case: a future 04:00-05:00 bulletin job (FR-020) must wait for it or move.
  `deploy_prod.sh` takes no lock (as before).
- Steps collect 2400 s, screen 2700, texts 900, screen-b 900; worst case 9060 s < `TimeoutStartSec`
  9600 (test, mutation killed). Exit always 0; container removed after a failed step.
- Deploy: only the world unit's timeout and description change. `world report` read-only (journal
  `?mode=ro`). `archive status` exclusion covered. Docs match.
- Mutations: 16, all killed.

Nice to have: reword the stdout comment in `run_daily_world_job.sh` (collect only); a note in
`docs/deploy.md` that a deploy during a long world run is not guarded by the lock.
