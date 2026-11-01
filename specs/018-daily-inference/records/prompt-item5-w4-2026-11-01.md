# Prompt: spec 018 item 5, W3 follow-ups and world stream step W4 collect job (2026-11-01)

You do two things in order: (1) a follow-up commit on the W3 branch (PR #164), (2) step **W4** as a
new PR branched from the W3 branch. Repo: `ai-news-collector`
(`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not merge, tag or deploy; no
ssh; no paid calls.

## Rules

- Work only in your own isolated worktree (`git fetch origin` first). Never edit, commit or pull in
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself; you may read files there. Do not edit the W3
  implementer's worktree `.claude/worktrees/agent-a2a8354462d61fb67`; check out
  `origin/feat/018-world-w3-storage` in your own worktree instead.
- Run Python as `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`.
  pytest prints no summary by default: use `-o addopts="" ... | tail -1`.
- Read `AGENTS.md` first and follow it: the feature doc `src/app/core/world/world.md` **before**
  code; every rule names its tests or says it has none; small patches in the surrounding style.
- Network: at most 3 real GDELT files for one manual smoke run; unit tests use fixtures and fake
  transports only.
- Local PostgreSQL: you may create a throwaway database in the Docker container `ainews-pg-test`
  (port 55432; read credentials with `docker inspect`), run the migration there, and drop that
  database afterwards. Do not touch any other container or database (`ai-news-db-local` holds the
  owner's local data).

## Read

1. On the W3 branch: `world.md`, `src/app/storage/world.py`, `tests/unit/test_world_storage.py`,
   `src/app/core/world/gdelt.py` and its `ai-news world scan` command.
2. Review of W3: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/018-daily-inference/records/review-item5-w3-2026-11-01.md`
   and the W3 report `report-item5-w3-2026-11-01.md` next to it (API notes "For W4").
3. Plan `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md` 6.1 (Schedule,
   Failure handling) and 6.2 step 4.
4. Patterns: `scripts/run_daily_archive_job.sh`, `scripts/install_daily_timers.sh`, their tests, and
   how deploy installs timers (find it; say in the report whether a deploy starts the new timer).

## Part 1: W3 follow-up commit (push to `feat/018-world-w3-storage`, PR #164)

Decided by the coordinator from the review:
- Single writer: state in `world.md` as an invariant that only the W4 job (under the host lock)
  writes world tables; keep check-then-insert. No `ON CONFLICT` change.
- FR-016 scan: resolve relative imports (`node.level > 0`); add the check that `app.core.world`
  never imports `app.storage` (review items 2 and 4). Show in the report that a relative-import
  mutation now fails the test.
- Tests for the untested rules: URL cut, batching over `HASH_CHUNK`, `error` cut, prune cutoff
  boundary, empty batch (item 3).
- `transition` raises `InvalidTransition` for an unknown stored state (item 5).
- PostgreSQL: run `upgrade head`, `downgrade -1`, `upgrade head` and a small upsert/prune round on a
  throwaway database in `ainews-pg-test`; write the result in the PR body; the doc rule then says how
  PostgreSQL was checked (manual, date), since CI has no PostgreSQL test.
- Item 6 (`server_default`): leave as is.

## Part 2: W4 PR (branch from the updated W3 branch)

- `ai-news world collect --date YYYY-MM-DD` (default: yesterday UTC): for each of the day's file
  stamps (primary and translation), skip `done_files`, otherwise scan the file with the W2 reader
  (streamed, one file at a time, no raw file kept), `upsert_candidates`, `record_file(... "done" |
  "missing" ...)`, commit per file so a crash loses at most one file. Then `prune()`. A limit option
  for smoke runs (`--max-files N`) is fine.
- Partial day by the plan's rule (more than 8 missing of 192 files); one summary log line
  `world_collect_finished` with files, rows, matched, kept, new, repeats, missing, partial, pruned.
- Switch `WORLD_COLLECT_ENABLED`, **default off**: when off, the job script logs one line and exits
  0 without downloading. Turning it on in production is a later, separate owner decision (about
  820 MB download per day). The CLI command itself works regardless of the switch.
- `scripts/run_daily_world_job.sh` shaped like the archive job (host lock, release image, `timeout`,
  always exit 0, one log line); unit and timer `ai-news-daily-world` at 04:00 UTC in
  `scripts/install_daily_timers.sh`. Document the switch and the job in `docs/` operator guides
  where the other jobs are (configuration, deploy), without repeating Behavior.
- Doc first: extend `world.md` (Behavior with flow diagram, Decisions, Invariants, Code map).
- Tests from plan 6.2 step 4: `test_collect_resumes_without_reprocessing_files`,
  `test_collect_partial_day_flag`, `test_world_job_script_is_isolated`,
  `test_install_timers_includes_world`; plus switch-off and commit-per-file tests.
- Smoke: one run of `ai-news world collect --max-files 3` on a temp SQLite file; counts in the PR
  body; delete the temp file.

## Checks (each PR)

ruff on `src tests`; scoped tests; `make lint PYTHON=...`; full pytest `-o addopts="" | tail -1`;
`scripts/check_code_docs.py`; `bash -n` on changed scripts. Advisory: `~/tools/unclebob/dryer/dryer`
and `~/tools/unclebob/crapper/crapper --no-coverage` on the changed source files (report duplicates
>= 0.8 and complexity >= 10; delete `.metrics/` afterwards).

## PRs

Copy this prompt into `specs/018-daily-inference/records/` of the W4 branch. Commit messages end with
a `Co-Authored-By:` line naming the model that wrote them. W4: `gh pr create --base master` (state
in the body that it stacks on #164 and must merge after it), title
`feat(018): world stream W4 collect job`; bodies list changes, checks with counts, and end with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

Both results (commit on #164, W4 PR link and branch, worktree path); files; checks with counts;
PostgreSQL result; smoke numbers; whether a deploy starts the timer; anything decided by you (one
line each); questions for the owner only if about money or what readers see.
