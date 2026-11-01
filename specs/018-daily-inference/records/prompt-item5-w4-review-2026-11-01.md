# Prompt: review of PR #166 (W4 collect job) and commit ef286a1 on PR #164 (2026-11-01)

You review (a) commit `ef286a1` on `feat/018-world-w3-storage` (PR #164, follow-ups to the first
review) and (b) PR #166 (`feat/018-world-w4-collect`, stacked on #164: review only its own commits
on top of #164). You did not write them. **Read-only: no commits, pushes, merges, PR comments, paid
calls or production access. No network to GDELT.** Report in English.

## Read

- `gh pr view`, `gh pr diff`, `gh pr checks` for 164 and 166; `git show ef286a1`.
- Implementer worktree (do not edit it): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-af35e7ac12d5a27e3`.
  For W4, check out `origin/feat/018-world-w4-collect` in your own worktree under your scratchpad.
- `AGENTS.md`; plan `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md` 6.1
  (Schedule, Failure handling) and 6.2 step 4; the W4 prompt `records/prompt-item5-w4-2026-11-01.md`.
- First review and reports in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/018-daily-inference/records/`:
  `review-item5-w3-2026-11-01.md`, `report-item5-w4-2026-11-01.md` (judge each decision there).

## Check

1. `ef286a1`: each first-review item is really fixed; the new tests are not vacuous (relative-import
   scan, core never imports storage).
2. `world collect`: skips `done_files`, commits per file, a crash loses at most one file; partial
   rule (more than 8 missing of 192) and the 12-missing-in-a-row stop; summary line fields; prune
   called; streaming invariant from W2 still holds (one file at a time, nothing raw kept, bounded
   memory: prod has 2 GB RAM).
3. "Only yesterday": after a missed night (outage, failed deploy) is the day lost unless someone runs
   it by hand? Judge against the plan's "catch-up after an outage" and propose the smallest fix if
   needed (for example, also process D-2 when it is not complete).
4. Switch `AINEWS_WORLD_COLLECT_ENABLED`: default off really means no download; how the job script
   reads it from env or host `.env` (quoting, `true`/`1` parsing, spaces); the CLI ignores it by
   design.
5. Job script and timer: same shape as `run_daily_archive_job.sh` (host lock shared with the other
   jobs, release image, `timeout`, exit 0, one log line); timeout 3300 s vs unit 5400 s; order with
   the 01:00-03:00 jobs; `deploy_prod.sh` enables the timer on deploy.
6. `gdelt.py` refactor (`scan_file`, `FileResult`) keeps W2 behavior.
7. Doc `world.md` matches the code; every rule names tests or says none; `docs/` guides do not
   repeat Behavior; `scripts/check_code_docs.py`.
8. Tests check behavior, not mocks; missing cases.
9. Run in your W4 worktree:
   `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_world_collect.py tests/unit/test_world_storage.py tests/unit/test_world_gdelt.py tests/unit/test_daily_timers.py tests/unit/test_deepseek_digest.py | tail -3`,
   ruff on `src tests`, `bash -n scripts/run_daily_world_job.sh scripts/install_daily_timers.sh`.
10. Advisory: `~/tools/unclebob/dryer/dryer` and `~/tools/unclebob/crapper/crapper --no-coverage` on
    `src/app/core/world_collect.py src/app/core/world/gdelt.py`; report duplicates >= 0.8 and
    complexity >= 10; delete `.metrics/` afterwards. Remove your worktree when done.

## Report (final message)

Per item (a) and (b): verdict (merge / merge after fixes / do not merge); findings by severity with
file:line, the concrete failure and a one-line fix; "must fix" separate from "nice to have"; checks
you ran with results.
