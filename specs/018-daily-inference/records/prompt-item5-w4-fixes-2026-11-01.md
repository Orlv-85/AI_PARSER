# Prompt: fixes to PR #166 (W4) from review (2026-11-01)

Sent to the W4 implementer agent (same context). Push fix commits to `feat/018-world-w4-collect`
(PR #166). Same rules as `prompt-item5-w4-2026-11-01.md`: own worktree, no merge, tag, deploy, ssh
or paid calls; doc first; test first (AGENTS.md, Code Changes, merged in #165: write the failing
test, see it fail, then the smallest code).

Review: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/018-daily-inference/records/review-item5-w4-2026-11-01.md`.

Decided by the coordinator:

1. Sudoers (must fix). The coordinator verified prod: `/etc/sudoers.d/ai-news-deploy` has no world
   entries, so the deploy would fail. Keep the exact-arguments model. In `docs/deploy.md`: "six" ->
   "eight" unit files, and a one-time server setup step listing the exact sudoers lines to add (two
   `install` lines for `ai-news-daily-world.service` and `.timer`, and `systemctl enable --now
   ai-news-daily-world.timer`), to be applied by root before the first deploy that contains W4.
   Make sure every sudo call in `install_daily_timers.sh` matches a documented line exactly (also
   any `disable` path). Update `docs/archive/...` nothing. Do not touch the server.
2. D-2 catch-up (should fix): the job collects D-1, then D-2 (no download when D-2 is complete).
   Doc rule and tests (missed night recovered; complete D-2 costs no download).
3. Prune test: seed a 31-day-old candidate and file row, run collect, assert both pruned counts.
4. `.env` parsing: strip `\r` and trailing blanks/comments, accept `export X=`; tests for quoted
   values, last-wins, CRLF; document accepted true values (`true`, `1`, `yes`, `on`, any case).
5. `skipped` count after the 12-missing stop: count done files after the break as skipped; test.
6. `partial`: not stored; add a doc note that W5/W6 derive it from `done_files` with the constant.
7. `docs/deploy.md`: name the constant instead of "8 of 192"; fix the over-long line in `world.md`.

Checks: ruff, scoped tests, `make lint PYTHON=...`, full pytest `-o addopts="" | tail -1`,
`check_code_docs.py`, `bash -n`; advisory dryer/crapper on changed sources. Update the PR #166 body.

Report: commits, files, checks with counts, the exact sudoers lines for the owner, anything decided
by you (one line each).
