# Prompt (Codex, gpt-6.1-sol high): spec 018, a world story is not repeated on the next day (2026-11-05)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`fix/018-world-no-repeat`, from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/world-no-repeat`. Do not touch any
other directory. Do not run git commit, push or any gh command. No network, no paid calls. Do not
spawn a doc review or any sub-agent: a separate reviewer (another model) reviews the code and the
doc after you.

Speed rule: while working run only the feature's tests and `ruff` on changed files; at the end run
the full suite, `make lint`, crapper, dryer and mutator once each, in that order; after a fix rerun
only the check that failed.

Commands: `E="env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 PYTHONDONTWRITEBYTECODE=1"`,
pytest is `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest`.

## Problem

With `world_stream_in_bulletin` on, `load_day_input` (`src/app/storage/bulletin_input.py`,
`_world_candidates`) takes assessed world candidates from `WorldRepo.candidates_in_window`, which
covers GDELT days `D-1` and `D`. So a world story can be selected for the bulletin of `D-1` and again
for `D`. Production data of 2026-11-04/05 shows the same stories in both windows (e.g. "Canva ...
job cuts"). Nothing checks earlier bulletins. The switch is off in production; it will be turned on
after this fix.

## Rule (decided 2026-11-05 (agent), owner yes to "fix, then turn on")

A world candidate of day `D` is left out when the stored bulletin of day `D-1` (row from
`BulletinRepo(session).get(D - 1)`, status `ready`) already has a story with the same story: any of
that story's `links[].url` equals the candidate's `url`, or `cluster_key` (from
`src/app/storage/world.py`) of the stored story's `title` equals `cluster_key` of the candidate's
title (syndicated copies on other domains). Compare against every story of that payload, whatever
its `origin` (Key results, rubric story, Cooperation, incident story). No row, a skipped row or an
unreadable payload means nothing is left out. Digest candidates are unchanged. Only `D-1` is checked:
the window is two days, so a story cannot reach a third bulletin.

## Steps (doc first, then failing tests, then code)

1. Read `AGENTS.md`, `src/app/core/bulletin/builder.md` (it covers `bulletin_input.py`),
   `src/app/storage/bulletin_input.py`, `src/app/storage/bulletin_store.py` and
   `src/app/storage/bulletin_store.md` (payload shape: `key_results`, `rubric_story`, `cooperation`,
   `incident_story`, each story with `title` and `links`), `src/app/storage/world.py`
   (`cluster_key`, `candidates_in_window`), and `tests/unit/test_bulletin_builder.py` (the world
   candidate tests and their fixtures).
2. Doc: in `builder.md` Behavior add the rule above next to the world-candidates rule, with its
   test names; one Decisions line "decided 2026-11-05 (agent): the world window spans two GDELT
   days, so a story would otherwise run on two consecutive days; only D-1 is checked"; Code map
   row if a new helper appears.
3. Failing tests first (run them, see each fail for the expected reason), in
   `tests/unit/test_bulletin_builder.py` or next to the existing `load_day_input` tests:
   - `test_world_candidate_shown_yesterday_is_left_out` (same URL in a ready D-1 bulletin)
   - `test_world_candidate_syndicated_copy_shown_yesterday_is_left_out` (other URL, same
     `cluster_key` title)
   - `test_world_candidate_kept_when_yesterday_skipped_or_missing` (no row; skipped row)
   - `test_world_candidates_not_compared_beyond_yesterday` (same story in the D-2 bulletin is kept)
   - `test_digest_candidates_ignore_yesterday` (a digest article whose URL was in D-1 stays)
4. Code: the smallest change in `bulletin_input.py` (a helper that collects the URLs and title
   keys of D-1, used by `_world_candidates`). Keep functions under CRAP 10.
5. Checks once at the end, in this order, from the worktree root:
   - `$E /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q` (full suite)
   - `$E make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`
   - `$E ~/tools/unclebob/crapper/crapper src/app/storage/bulletin_input.py`
   - `~/tools/unclebob/dryer/dryer --threshold 0.8 src/app/storage/bulletin_input.py`
   - `$E ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_bulletin_builder.py" src/app/storage/bulletin_input.py`
     (kill survivors in the new code with tests, or give a reason per survivor).

## Report

Write `specs/018-daily-inference/records/report-world-no-repeat-2026-11-05.md` in the worktree:
files changed; the rule as implemented; each new test and how it failed before the code; full-suite
and lint results with counts; crapper (max CRAP of changed functions), dryer and mutator output
(killed/survived, reasons); anything not run and why.
