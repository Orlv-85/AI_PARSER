# Prompt (fresh Claude agent, Sonnet): review of feat/018-writer-reserve (2026-11-15)

Worktree: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/writer-reserve`
(branch `feat/018-writer-reserve`). Read only: no edits, no commit, push, gh, network, ssh or
sub-agents. The task the code was written from:
`specs/018-daily-inference/records/prompt-writer-reserve-impl-2026-11-15.md` (rules B1, W1, W2,
W3). Diff: `git diff origin/master...HEAD -- src tests` (skip `specs/`).

The change decides which stories readers see and makes the one paid writer call bigger. Check, in
this order, and stop reading a file once its question is answered:

1. `src/app/core/bulletin/builder.py`: with the reserve, is the set and order of Key results,
   rubric, Cooperation, incident story, headline, numbers and reactions exactly what it was
   before for every input (the loop in `_key_results` now runs to `KEY_RESULTS_MAX + RESERVE_MAX`:
   can a cap such as `MODEL_LAUNCHES_MAX` or a skip now change which stories are the first four)?
   Can a reserve story also be the rubric, a Cooperation or the incident story?
2. `src/app/core/bulletin/writer.py`: can a reserve story reach readers without a checked model
   headline and site sentence (title fallback, `_fallback`, an invalid or partial model answer, a
   missing entry for a reserve id, a non-English reserve story without Telegram text)? Can the
   stored payload, `render_text` or the web page (`src/app/web/bulletin_view.py`) show or store
   the reserve? Are the `dropped` ids of the summary still the packet ids after promotion, and
   can `s<N>:story:non_english_title` point at the wrong story? Is the day headline ever taken
   from or grounded in a reserve story, and what happens to a model day headline when the story it
   is about was removed and a reserve story took the place?
3. Money: `WRITER_MAX_OUTPUT` went from 4096 to 6144. From `_reservation` in
   `src/app/usecases/bulletin/writer_run.py` and `STORY_TEXT_MAX`/`build_packet`, estimate the
   reservation of a 12-story packet against `WRITER_MAX_USD_PER_DAY`, and say how many writer
   calls plus repeat-check calls fit in one day's cap (a manual rebuild of other dates uses the
   same journal).
4. Tests in `tests/unit/test_bulletin_reserve.py`: for each rule B1, W1, W2, W3 name one
   one-line change in the code that no test would catch, if there is one.
5. Docs: do `builder.md` and `writer.md` state the behavior the code has (not more)?
6. Run only: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_bulletin_reserve.py tests/unit/test_bulletin_writer.py tests/unit/test_bulletin_writer_language.py tests/unit/test_bulletin_builder.py tests/unit/test_bulletin_store.py tests/unit/test_web_bulletin_page.py`.

Final message: verdict (approve / fix needed), then findings as a list, most serious first:
file:line, what is wrong, the concrete input that shows it. No praise, no summary of the diff.
