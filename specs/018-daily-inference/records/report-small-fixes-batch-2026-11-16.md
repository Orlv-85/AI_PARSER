# Report: spec 018 small fixes batch (2026-11-16)

Implementer: background Claude agent (Sonnet), prompt `prompt-small-fixes-batch-2026-11-16.md`.
Saved by the coordinator from the agent's final message (agents cannot write report files);
shortened, facts kept.

## Process
- Docs of fixes 1 and 5 were written after the code, not before; fix 2's failing test came first,
  its doc after the code. The coordinator read the diff against the prompt's rules; a fresh agent
  reviews the doc wording.

## Fix 1, day headline of a removed story (`writer.py`)
- `_remove_and_recheck` replaces the bare `_remove_non_english_stories` call in `write_bulletin`:
  maps shown stories to ids before the removal; when a story was removed and the headline is from
  the model, re-checks the raw headline with `sentence_error(min_chars=8)` against the evidence of
  the stories that stay; on failure headline None, no cut, origin `title`,
  `headline:removed_story`. Runs before the promotion.
- Tests (`test_bulletin_reserve.py`): `test_day_headline_of_a_removed_story_is_dropped` (failed
  first: `assert 'ORBIX PRESENTS CHEAPER LANGUAGE SYSTEM' is None`),
  `test_day_headline_of_a_kept_story_survives_a_removal` (guard of the unchanged case, passes
  before and after).

## Fix 2, R1 record and empty title key (`builder.py`, `day_input.py`, `daily.py`)
- `ToldBefore(title, match, published_day)`, `DayInput.told_before`. `_recent_story_keys` maps URL
  and non-empty title key to the latest stored day; `_told` matches; `_split_shown` returns
  `(kept, digest_left_out, told)`. `prepare_from_input` adds `numbers["told_before"]`; the
  `bulletin_assessed_share` log keeps the two counts.
- New `tests/unit/test_bulletin_told_before.py`: `test_told_before_records_url_match`,
  `test_told_before_records_title_match`, `test_empty_title_key_does_not_match`,
  `test_numbers_list_told_before` (failed first: `ImportError: cannot import name 'ToldBefore'`).
- Existing expectations got `"told_before": []` (`NUMBERS` in `test_bulletin_store.py`, one
  assertion in `test_bulletin_daily.py`).

## Fix 3, writer journal that cannot open (`daily.py`)
- `write_prepared` calls `_write_with_journal`: only the opener is guarded (`OSError`,
  `sqlite3.Error`, `ValueError`); on failure logs `bulletin_writer_journal_failed`, runs
  `write_bulletin` with an ask answering `journal_unavailable`, `cost_usd` 0.0.
- Tests (`test_bulletin_daily.py`): `test_write_prepared_survives_a_journal_that_cannot_open`
  (failed first: `OSError: disk` propagated), `test_run_daily_stores_the_day_when_the_writer_journal_fails`
  (failed first: stored `skipped`, not `ready`).

## Fix 4, stale daily.md line
- `bulletin_home_page` is read at `src/app/web/routes/pages.py:177` (`_home_response`);
  `bulletin_post_channels` is only in `settings.py:67` (no consumer). No test.

## Fix 5, shared-word guard for model repeats (`repeats.py`)
- `REPEAT_MIN_WORD = 5`, `WORD`, `_words`, `_shares_word`; `_apply` drops only pairs that share a
  word with the shown or original published title; summary `kept` (`reason: no_shared_word`).
  `REPEATS_VERSION` unchanged.
- Tests (`test_bulletin_repeats.py`): `test_repeat_without_a_shared_word_is_kept` (real titles),
  `test_repeat_with_a_shared_word_is_dropped`, `test_shared_word_may_come_from_the_original_title`,
  `test_short_words_do_not_count_as_shared` (failed first on the missing `kept` key and the wrongly
  applied pair). Fixtures changed so older drop tests share a word: `PUBLISHED` original in
  `test_bulletin_repeats.py`, `store_previous_day` title in `test_bulletin_daily.py`.

## Checks (worktree, PYTHONPATH=src)
- pytest `tests/unit/test_bulletin_*.py test_web_bulletin_page.py test_layer_imports.py
  test_monkeypatch_targets.py test_code_docs.py`: 554 passed, 1 warning.
- ruff: all checks passed. pylint on changed files: 10.00/10.
- crapper `--changed`: every changed function under 10 (largest `_remove_and_recheck` 6); the
  untouched `_repeat_pairs` (`repeats.py`) is at 10.0. dryer 0.8 `--changed`: no duplicates. With
  explicit paths both tools printed "No source files to analyze".
- Full repo gate not run (CI runs it).

## Not from this task
- `build/requirements.txt` (`fastapi` 0.163.0 -> 0.163.1) was added to the branch by the
  coordinator on the owner's word, not by the implementer.

## Review (fresh Claude agent, Sonnet, prompt `prompt-small-fixes-review-2026-11-16.md`)
Verdict: approve. Findings, fixed by the coordinator test first:
1. A journal failing to close (`ExitStack` exit) after the writer answered still lost the day;
   the same for the repeat check. Now `_close_journal` closes after the answer and logs
   `bulletin_writer_journal_close_failed` / `bulletin_repeats_journal_close_failed`. Tests:
   `test_daily_writer_journal_that_fails_to_close_keeps_the_answer`,
   `test_daily_repeat_journal_that_fails_to_close_still_stores` (both failed first: day not stored).
2. `float(max_usd)` inside the guard turned a bad limit into a title-only bulletin. Now computed
   before the guard. Test: `test_write_prepared_bad_max_usd_is_not_a_journal_fault` (failed first:
   DID NOT RAISE).
Left as noted: a fault inside the writer body propagates (no test, unchanged behavior); test
fixtures of older repeat tests were changed to share a word.

After the fixes: test_bulletin_daily, test_code_docs, test_monkeypatch_targets,
test_bulletin_told_before pass; ruff clean; pylint 10.00; crapper with coverage (LCOV of the
bulletin tests): every changed function under 10 (largest `repeats._apply` 9), untouched
`_repeat_pairs` at 10.0; dryer 0.8: no duplicates.
