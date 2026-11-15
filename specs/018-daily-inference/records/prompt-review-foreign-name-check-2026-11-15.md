# Prompt (fresh Claude agent, Sonnet): review of fix/018-foreign-name-check (2026-11-15)

Worktree: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/foreign-name-check`
(branch `fix/018-foreign-name-check`). Read only: no edits, no commit, push, gh, network or
sub-agents.

Change (see `git diff origin/master -- src tests`): the bulletin writer's name check
(`src/app/core/bulletin/writer_grounding.py`, `_evidence_error`) now lets "AI" (`SUBJECT_WORDS`)
and the common nouns of `HEADLINE_OPENERS` pass without standing in the article text;
`WRITER_VERSION` is `bulletin-writer-6`. Reason and rule: `src/app/core/bulletin/writer.md`
(Grounding 5, Decisions 2026-11-15). The `records/` files in the diff are documents: skip them.

Check and report, briefly:
1. Does the code do what the doc says, and nothing more? In particular: can a real name now pass
   unchecked (a word of `HEADLINE_OPENERS` that is also part of a name; "AI" inside a longer
   token such as "OpenAI", "xAI", "AI21"; case and `'s` forms)? Read `grounding_error` in
   `src/app/core/daily/signals_brief.py` and `_words` to answer.
2. Do the three new tests in `tests/unit/test_bulletin_writer.py` pin the rule (would they fail
   if the rule were removed or widened to "any first word")? Name a missing case if any.
3. Any other place that pins the writer version or the starters and was not updated
   (`grep -rn "bulletin-writer-5" src tests docs`).
4. Run only: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_bulletin_writer.py tests/unit/test_bulletin_writer_language.py`.

Final message: verdict (approve / fix needed), then findings as a list: file:line, what is wrong,
the concrete input that shows it. No praise, no summary of the diff.
