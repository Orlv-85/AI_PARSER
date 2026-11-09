# Prompt (Codex, gpt-6.1-sol high, resume): writer F9 review fixes (2026-11-09)

Same worktree and rules as your task (`prompt-writer-f9-f1-codex-2026-11-09.md`): no commit, push,
gh, network, paid calls or sub-agents; `PYTHONPATH=src` on every pytest run. The coordinator
committed your work (PR #219). Review (Astra) asked for two changes. Doc first (`writer.md`), then a
failing test for each, then code.

1. **A non-English day headline survives when its story stays.** If the day headline is the
   builder's title headline (`headline_origin == "title"`) made from the title of any known
   non-English world story (kept or removed), clear it the same way as for a removed story
   (`headline = None`, `headline_cut = False`). Test: `test_day_headline_from_kept_non_english_story_is_cleared`
   (German story keeps a valid model headline and Telegram note; the model day headline fails).
2. **A foreign title can survive as a gloss.** For a known non-English world story, drop its gloss
   when the gloss repeats a run of `GLOSS_TITLE_RUN_WORDS` (3) consecutive words of the story's
   original title (compare with the writer's existing `fold`); the drop is recorded as
   `<sid>:gloss:non_english_title`. The story itself stays when headline and Telegram note pass.
   Tests: `test_gloss_echoing_non_english_title_is_dropped`,
   `test_gloss_of_non_english_story_without_title_run_stays`.

Checks once at the end, in this order: full suite (`$E .../pytest -q -o addopts=`), `make lint`,
`python scripts/check_code_docs.py` (without `--diff`), crapper, dryer 0.8 and mutator on
`writer.py` with the feature test files. After a fix rerun only the check that failed.

Append a section "Review fixes" to `specs/018-daily-inference/records/report-writer-f9-f1-2026-11-09.md`:
each fix, its test and how it failed first, check results with counts, CRAP, survivors.
