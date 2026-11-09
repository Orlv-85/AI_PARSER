# Prompt (Codex, gpt-6.1-sol high): spec 018, writer fixes F9 (no non-English fallback) and F1 (actual speaker) (2026-11-09)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`fix/018-writer-f9-f1`, from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/writer-f9-f1`. Do not touch any
other directory. Do not run git commit, push or any gh command. No network, no paid calls. Do not
spawn a doc review or any sub-agent: a separate reviewer (another model) reviews after you.

Speed rule: while working run only the feature's tests and `ruff` on changed files; at the end run
the full suite, `make lint`, the doc check, crapper, dryer and mutator once each, in that order;
after a fix rerun only the check that failed.

Commands: `E="env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 PYTHONDONTWRITEBYTECODE=1"`;
pytest is `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest` (always with `PYTHONPATH=src`).

## Why

FR-022 batch 2 (`specs/018-daily-inference/records/review-summary-2026-11-05..08.md`, owner yes
2026-11-09 to F9 and F1 now):
- F9: when the model headline of a world story fails a check, the site and Telegram show the
  original article title, which for world stories is often not English (German, Chinese, Danish,
  Portuguese, French, Vietnamese seen in 4 days). ER-12 requires English output.
- F1: the writer put an outlet's own comparison in a company's mouth ("Anthropic says the tool
  follows similar features that OpenAI introduced ..." where TechCrunch made the comparison).

## Rules (decided 2026-11-09; owner yes for the reader-visible part)

F9. A world candidate keeps its GDELT language. In production, English rows carry `unknown` (the
GDELT English feed has no translation field) and translated rows a code like `deu`, `zho`, `vie`
(`src/app/core/world/gdelt.py`, column `world_candidates.language`). A story whose title language is
known and not English (`language` not in {`unknown`, `eng`, empty}) is published only with a model
`headline` **and** at least one `telegram_note` sentence that passed the checks; otherwise the whole
story is removed from the bulletin after the writer's checks (all sections; the story count
`incidents` is not changed). The removal is listed in the writer summary (`dropped` gets
`<sid>:story:non_english_title`). Digest stories are unchanged. If the call failed and the whole
bulletin is title-only, non-English stories are removed too. A day headline taken from a removed
story's title falls back the same way the builder's title headline does when no story qualifies
(read `builder.md`, keep the existing behaviour for a missing headline).

F1. `WRITER_PROMPT` adds: attribute each statement to whoever made it in the source; a comparison,
context or judgement written by the outlet stays the outlet's ("TechCrunch notes ...") or is stated
without a speaker only when it is plain fact in the source; never "X says" for words X did not say.
`WRITER_VERSION` becomes `bulletin-writer-5`.

## Steps (doc first, then failing tests, then code)

1. Read `AGENTS.md`, `src/app/core/bulletin/writer.md`, `src/app/core/bulletin/builder.md` (Story,
   headline of the day, world candidates), `src/app/storage/bulletin_store.md` (payload),
   `src/app/storage/bulletin_input.py` (`_world_candidates`), `src/app/core/bulletin/builder.py`
   (`Candidate`, `Story`, `as_dict`), `src/app/core/bulletin/writer.py` (`write_bulletin`, checks,
   summary), `src/app/core/world/gdelt.py` (`LANGUAGE_UNKNOWN`), and the tests
   `tests/unit/test_bulletin_builder.py`, `tests/unit/test_bulletin_writer*.py`.
2. Doc: `writer.md` Behavior (the F9 rule with test names; the F1 sentence in the prompt rules;
   version `bulletin-writer-5`), `builder.md` (Story carries the title language; world candidates
   pass it), `bulletin_store.md` if the payload gets a new key (old rows without it read as
   unknown). Decisions: "decided 2026-11-09 (agent): drop rather than translate a non-English
   title: a translation would be unchecked model text" and "GDELT English rows have no language".
3. Failing tests first (run them, see each fail for the expected reason), at least:
   `test_world_story_language_reaches_story`, `test_non_english_story_without_headline_is_removed`,
   `test_non_english_story_without_telegram_is_removed`, `test_non_english_story_with_model_text_stays`,
   `test_unknown_or_english_language_story_falls_back_to_title`,
   `test_title_only_bulletin_removes_non_english_stories`, `test_removed_story_is_in_dropped`,
   `test_day_headline_not_from_removed_story`, `test_old_payload_without_language_reads_unknown`
   (if a payload key is added), and extend `test_prompt_pins_its_rules` for F1 and the version.
4. Code: the smallest change; functions under CRAP 10.
5. Checks once at the end, in this order, from the worktree root:
   - `$E /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts=` (full suite)
   - `$E make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`
   - `$E python scripts/check_code_docs.py --diff origin/master --strict` (fails on uncommitted
     work: then run without `--diff`, and say so)
   - `$E ~/tools/unclebob/crapper/crapper <changed src .py files>`
   - `~/tools/unclebob/dryer/dryer --threshold 0.8 <changed src .py files>`
   - `$E ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= <feature test files>" <each changed src .py file>`
     (kill survivors in new code with tests, or give a reason per survivor).

## Report

Write `specs/018-daily-inference/records/report-writer-f9-f1-2026-11-09.md` in the worktree: files
changed; the rules as implemented; each new test and how it failed first; full-suite and lint
results with counts; CRAP, dryer, mutator (survivors and reasons); anything not run and why.
