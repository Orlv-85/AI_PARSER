# Prompt: spec 018 item 5, world stream step W7 nightly wiring (2026-11-01)

You implement step **W7** of the world stream as one PR, branch `feat/018-world-w7-job`. Repo:
`ai-news-collector` (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English. Do not
merge, tag or deploy.

## Rules

- Your own isolated worktree, branch from `origin/master` (`git fetch origin` first). Never edit,
  commit, check out or pull in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself; you may read
  files there. Scratch worktrees named with your step; never remove one you did not create.
- Run Python as `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`.
  pytest prints no summary by default: use `-o addopts="" ... | tail -1`.
- Read `AGENTS.md` first and follow it, and the ub-mode skill (`~/.claude/skills/ub-mode`; its
  "Repository rules come first" section applies). Doc first, then a failing test you saw fail for
  the expected reason, then the smallest code. Small patches in the surrounding style.
- **No paid calls**, no ssh, no network in tests (fakes and fixtures only).
- Another agent works in parallel on a different step of spec 018; if `src/app/cli/main.py`
  conflicts at PR time, rebase on `origin/master` and resolve.

## Checks

ruff on `src tests`; scoped tests; `make lint PYTHON=...`; full pytest `-o addopts="" | tail -1`;
`scripts/check_code_docs.py --diff origin/master --strict` run alone after your last commit, report
its exit code. mypy: fix `no-any-return` with `cast` or a typed local, never `# type: ignore`;
`bash -n` on changed scripts. Advisory: `~/tools/unclebob/dryer/dryer` and
`~/tools/unclebob/crapper/crapper --no-coverage` on changed source files (report duplicates >= 0.8,
complexity >= 10; delete `.metrics/`).

## Read

1. `src/app/core/world/world.md` (all of it), `src/app/core/world_collect.py`,
   `src/app/core/world_screen.py`, `src/app/core/world_text.py`, `src/app/core/archive/capture.md`.
2. `scripts/run_daily_world_job.sh`, `scripts/run_daily_archive_job.sh`,
   `scripts/install_daily_timers.sh`, their tests, `docs/configuration.md`, `docs/deploy.md`.
3. Plan `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md` 6.1 (Schedule,
   Failure handling, Check before use) and 6.2 step 7; gate report
   `records/report-item5-w5-gate-2026-11-01.md`; W6 review `records/review-item5-w6-2026-11-01.md`
   (on master after the records PR; if not there yet, read it at
   `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/review-item5-w6-2026-11-01.md`).

## What to build

- Doc first (`world.md`, and `capture.md` for item 3).
- **Job**: the 04:00 UTC world job, still behind `AINEWS_WORLD_COLLECT_ENABLED` (default off: one
  log line, exit 0, no download, no Jev), runs for day D-1 in order: `world collect` (with its D-2
  catch-up), `world screen`, `world texts`, `world screen` again (step B on the new texts), all
  under the same host lock as the other jobs (`world texts` shares `data/archive/source-cache` with
  the archive job). Each step has its own timeout inside the unit's limit; a failed or timed-out step
  is logged and the next steps decide by their own state (a failed collect still lets screen work on
  what is stored). Always exit 0, one summary log line per step. Jev needs `JEV_API_KEY` from the
  host `.env` like the digest; without it the Jev steps log and skip. Set the timeouts from the gate
  numbers (collect about 4 min for a day; screen 1,842 requests: measure or estimate the time of a
  Jev request from the code's transport settings and state it).
- **Money**: no change; the world journal's $0.10 per UTC day cap applies to both screen runs.
- **First days check (FR-018)**: a read-only command `ai-news world report --date D` printing
  candidates, clusters, screened in/out, text_ready/no_text with reasons, assessed with
  `world_change` counts, cost of the UTC day from the world journal, and a sample of 20 assessed
  stories (title, domain, answers). Used later to write `records/world-days-<date>.md`; no file
  writing in the command.
- **W6 follow-ups**: archive `status` (`state_counts`, `hosts_without_text`) excludes world
  documents like coverage does (or shows them separately; decide, doc, test); a direct test that
  only `pending` documents are downloaded by `world texts` (mutation B7 of the W6 re-review).
- No bulletin switch here (item 2 adds `WORLD_STREAM_IN_BULLETIN`). Do not change other jobs or
  deploy defaults. Say in the report whether a deploy picks up the new job script (it runs from the
  release image or the host copy?).

## PR

Copy this prompt into `specs/018-daily-inference/records/` of your branch. Commit messages end with
a `Co-Authored-By:` line naming the model that wrote them. `gh pr create --base master`, title
`feat(018): world stream W7 nightly job and report`; body lists changes, checks with counts, and
ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

PR link, branch, worktree path; files; checks with counts and the doc-check exit code; timeouts and
how you set them; what turning `AINEWS_WORLD_COLLECT_ENABLED` on in production would do each night
(download, requests, cost, time); anything decided by you (one line each); questions for the owner
only if about money or what readers see.
