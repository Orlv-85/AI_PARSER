# Prompt (fresh Claude agent, Sonnet): review of feat/018-event-repeats (2026-11-15)

Worktree: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/event-repeats`
(branch `feat/018-event-repeats`). Read only: no edits, no commit, push, gh, network, ssh or
sub-agents. The task the code was written from:
`specs/018-daily-inference/records/prompt-event-repeats-impl-2026-11-15.md` (rules R1, R2, R3).
Diff: `git diff origin/master...HEAD -- src tests` (skip `specs/`).

This is a money path (one paid model call a day on the writer's journal) and it removes stories
readers would see. Check, in this order, and stop reading a file once its question is answered:

1. `src/app/core/bulletin/repeats.py`: can any model answer or provider fault raise, or remove or
   merge a candidate that the rules do not allow (ids, types such as bool/int/nested lists, an
   unhashable id, a candidate in two groups, `published` id out of range, empty groups)? Give the
   exact answer JSON that breaks it.
2. `src/app/usecases/bulletin/daily.py` (`_repeat_check`, `run_daily`): can the check make more
   than one paid call a run, run without the DeepSeek key, or stop the bulletin from being built
   and stored when the journal or provider fails (read `Writer.ask` and `open_writer` in
   `writer_run.py`: what if the opener itself raises, e.g. the daily cap or a locked journal)?
   Is a rerun of the same day free (same body, same journal key)?
3. `src/app/usecases/bulletin/day_input.py` (R1): any case where a story is wrongly left out:
   a rebuild of day D after D+1 exists, the same day's own stored bulletin, a follow-up article
   with the same first `CLUSTER_KEY_CHARS` characters of the title. Is `numbers["assessed"]`
   still the count of assessed digest articles?
4. The wiring tests in `tests/unit/test_bulletin_daily.py` were written after the code. For each
   of `test_daily_repeat_check_runs_before_the_build_and_is_stored`,
   `test_daily_invalid_repeat_answer_still_builds_every_story`,
   `test_daily_without_ds_key_makes_no_repeat_call`: name the one-line change in `daily.py` that
   should make it fail, and say from reading whether it would. Do not edit files to try.
5. Docs: do `repeats.md`, `builder.md`, `daily.md` state the behavior the code has (not more)?
6. Run only: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_bulletin_repeats.py tests/unit/test_bulletin_daily.py tests/unit/test_bulletin_builder.py`.

Final message: verdict (approve / fix needed), then findings as a list, most serious first:
file:line, what is wrong, the concrete input that shows it. No praise, no summary of the diff.
