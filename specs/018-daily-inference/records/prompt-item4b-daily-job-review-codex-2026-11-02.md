# Prompt (Codex review, gpt-6-astra high): spec 018 item 4b, daily bulletin job (2026-11-02)

Read-only review. Directory (git worktree of branch `feat/018-item4b-daily-job`, changes
uncommitted; compare with `origin/master`, include untracked files):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4b-daily-job`.
Do not edit files, commit, push or use gh. No network, no paid calls. Do not spawn a sub-agent.

The executor's prompt: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-018-item4b-daily-job-codex-2026-11-02.md`
(read it: scope, decisions already made, test names). Spec: `specs/018-daily-inference/spec.md`;
feature doc `src/app/core/bulletin/daily.md`.

## Check

1. `git diff origin/master` plus every untracked file, read in full.
2. Correctness with concrete inputs (`src/app/core/bulletin/daily.py`, `src/app/cli/main.py`):
   - `bulletin daily`: no digest, no Jev key, no DS key, skipped build, ready build, posted day
     (refused save). Is the summary right in each case, and is something stored where the doc says?
   - Writer failure (DeepSeek error, cap reached, timeout): the outer `except Exception` drops the
     whole run as `daily_failed` and stores nothing, although the build succeeded and the Jev
     answers are committed. Is that what `daily.md` says and is it the right choice, or should the
     unwritten bulletin be stored? Same question for an assessor failure: does the build still run?
   - Session state: `run_assessment` commits? After an exception inside `run_daily`, is a
     half-written transaction left or rolled back?
   - `bulletin build` refactor: behavior must stay the same as on `origin/master` (exit 2 on no
     digest, `--dry-run` stores nothing, skipped day stored, `--write` stores the written bulletin
     and numbers, JSON and text output, log events and their fields). List every difference.
   - `bulletin assess` refactor: same check (dry run, cap, `ValueError` -> exit 2).
   - Money: daily uses `ASSESS_DEFAULT_MAX_USD` and `WRITER_MAX_USD_PER_DAY`; can one run or a
     rerun the same day exceed the journal caps?
3. Scripts and production permissions:
   - `scripts/run_daily_bulletin_job.sh`: switch parsing, lock re-exec, exit 0 always, container
     name cleanup, `timeout -k`. Compare with `scripts/run_daily_world_job.sh`.
   - Timeout budget: lock wait 5400 + step 1800 + kill grace + removals vs `TimeoutStartSec=7500`
     in `scripts/install_daily_timers.sh`; is the margin real and checked by a test?
   - Schedule: world 04:00 UTC holds the same lock (its worst case), digest/archive times; can the
     bulletin run before D-1's digest or world screen finished? What happens then?
   - `deploy/sudoers.d/ai-news-deploy`: exactly the new unit installs and `enable --now` the
     installer runs; nothing wider. Do installer commands match sudoers lines byte for byte?
   - The `.env` parser is copied from the world script (about 40 lines): say whether to extract it
     to a shared file now (risk to the world job) or keep the copy.
4. Settings `bulletin_home_page`, `bulletin_post_channels`: default off, documented, used anywhere?
5. Docs: `daily.md` rules match code; every rule names existing tests; registrations in README
   files; edits in builder.md, writer.md, world_change.md, configuration.md, troubleshooting.md
   accurate.
6. Tests: would each fail if its code were reverted? Hand mutations (store on missing key path
   wrongly, drop the commit, skip the writer when DS key set, non-zero exit in script, wrong lock
   wait, timer time) and which tests kill them; name survivors.
7. Run: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_bulletin_daily.py tests/unit/test_daily_timers.py tests/unit/test_deepseek_digest.py tests/unit/test_bulletin_builder.py tests/unit/test_bulletin_store.py | tail -1`

## Report (your final message)

Findings ranked most severe first: file:line, problem, concrete failing input, one-line fix. Then
mutation results. Then "clean" if nothing must change before merge. Be brief.
