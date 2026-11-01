# Prompt: review of PR #193 (018 world stream W7, nightly job and report) (2026-11-01)

You review PR #193 (`feat/018-world-w7-job`). You did not write it. **Read-only: no commits,
pushes, merges, PR comments, paid calls, network or production access.** Never run any command that
changes `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself (no `gh pr checkout`, no `git checkout`
there); you may read files there. Report in English.

## Read

- `gh pr view 193`, `gh pr diff 193`, `gh pr checks 193`.
- Implementer worktree (do not edit it): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-a94586e8ceaf28db7`.
  For runs and mutations, create a worktree of `origin/feat/018-world-w7-job` under your scratchpad
  named with `pr193`; never remove one you did not create; remove yours at the end.
- `AGENTS.md` (Deploy And Ops: production-sensitive); the W7 prompt
  `records/prompt-item5-w7-2026-11-01.md` (on the branch); `scripts/run_daily_archive_job.sh`,
  `scripts/deploy_prod.sh` (or the deploy script that installs timers), other host-lock users.
- Implementer report (judge each decision):
  `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/report-item5-w7-2026-11-01.md`.

## Check

1. **Production safety (most important).** With `AINEWS_WORLD_COLLECT_ENABLED` off (the default and
   the current production state), does the job do nothing beyond one log line (no container, no
   download, no Jev, no lock held long)? Switch and key parsing from env and host `.env` (quoting,
   `true`/`1`, spaces, comments); the key never printed or logged (check `set -x`, error paths,
   docker args visible in `ps`).
2. The host lock: who else takes it (fetch, digest, archive, auto-update, deploy, db maintenance)?
   With the switch on, can a long world run (up to about 2 h) delay or break another job or a
   deploy? A future bulletin job at 04:00-05:00 UTC (spec FR-020) would wait: note it.
3. Step order, per-step timeouts, exit 0 always, one log line per step; `TimeoutStartSec` 9600 vs
   the sum (the test is real); a timed-out container is removed; a failed collect still lets screen
   run.
4. Deploy: the job script runs from the host checkout and the unit is reinstalled on deploy; no
   change to other jobs, ports, auth, retention or database behavior.
5. `world report`: read-only (no table creation, journal opened read-only, no files); counts and
   cost windows correct; FR-016 import list change narrow.
6. `archive status` exclusion of world documents; nightly archive unchanged otherwise.
7. Docs (`world.md`, `capture.md`, `docs/deploy.md`, `docs/configuration.md`, `docs/cli.md`) match
   the code without repeating Behavior in `docs/`; `check_code_docs.py --diff origin/master
   --strict` (exit code); `bash -n` on the scripts.
8. **Mutation checks**: at least 10 hand mutations (switch default, key skip, step order, a timeout
   value, exit code, lock name, unit timeout, report read-only guard, status exclusion, D-1 date);
   table killed/survived.
9. Run the changed test files and ruff on `src tests`.

## Report (final message)

Verdict (merge / merge after fixes / do not merge); findings by severity with file:line, the concrete
failure and a one-line fix; "must fix" separate from "nice to have"; mutation table; checks run.
