# Prompt: spec 018 small fixes batch (2026-11-16)

Owner go: "одним PR" (2026-11-16). Five fixes found by the reviews of #256/#257 and by the check of
the night bulletin of 2026-11-15. One branch, one PR.

## Where and how

- Work only in the worktree `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-small-fixes`
  (branch `fix/018-small-batch`, based on `origin/master` 9e0fe67). Never touch the main folder
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
- Read `AGENTS.md` first. Rules that matter here: feature doc first, then a failing test (run it,
  see it fail for the expected reason), then the smallest code; ASCII; catch only expected
  exceptions; match the style of the surrounding code; do not edit unrelated files.
- Python: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`. In the worktree always
  run with `PYTHONPATH=src` (pytest and pylint), and with `set -o pipefail` when piping.
- Do not commit, push or open a PR. The coordinator does that.
- Test files must stay under 1000 lines (pylint too-many-lines). `tests/unit/test_bulletin_builder.py`
  is already 1016 lines and `test_bulletin_writer.py` 981: put new tests in other or new files
  (named below).

## Fix 1. Day headline about a removed story (writer)

Files: `src/app/core/bulletin/writer.py`, `src/app/core/bulletin/writer.md`, tests in
`tests/unit/test_bulletin_reserve.py`.

Problem: the model day headline is checked (names and numbers, `sentence_error`) against the
evidence of all shown stories in `parse_writer`. Later `_remove_non_english_stories` can remove
shown stories; a model day headline whose names or numbers came only from a removed story stays
above the stories that replaced it.

Rule (write it into `writer.md` Behavior, next to the reserve / removal rules, with test names):
after the removal and before the reserve promotion, when at least one shown story was removed and
the day headline came from the model, the raw model day headline (the string `parse_writer`
returned, before `.rstrip(".").upper()`) is checked again with `sentence_error(headline, evidence,
min_chars=8)` against the evidence (`_evidence`) of the shown stories that stay (not the reserve,
not the removed ones). If it fails, the day headline becomes absent (`headline=None`,
`headline_cut=False`, `headline_origin="title"`) and `dropped` gets `"headline:removed_story"`.
Nothing changes when no story was removed. Like the other checks this is of names and numbers, not
of topic: a headline about a removed story in common words still passes (say so in the doc).

Implementation hint: in `write_bulletin`, before `_remove_non_english_stories(result, dropped)`,
map each shown story object to its packet id (`s1..sN`, the order of `all_stories(result)`); after
it, collect the ids of the stories still in `all_stories(result)` and join `_evidence(entry)` of the
matching `packet["stories"]` entries. Keep `write_bulletin` short (a helper function; CRAP < 10).

Tests (write first, see them fail):
- `test_day_headline_of_a_removed_story_is_dropped`: two shown stories, one known non-English world
  story whose model text has no telegram note (so it is removed); the model day headline names a
  name found only in the removed story's article; result: `headline is None`,
  `headline_origin == "title"`, `"headline:removed_story" in summary["dropped"]`.
- `test_day_headline_of_a_kept_story_survives_a_removal`: same, but the headline's name is in the
  kept story; the headline stays, origin `model`.

Look at the existing helpers of `test_bulletin_reserve.py` and reuse them.

## Fix 2. Record what the free repeat check (R1) left out; empty title key never matches

Files: `src/app/core/bulletin/builder.py` (`DayInput`), `src/app/usecases/bulletin/day_input.py`,
`src/app/usecases/bulletin/daily.py`, docs `src/app/core/bulletin/builder.md` (where R1 is
described) and `src/app/usecases/bulletin/daily.md` (numbers), new test file
`tests/unit/test_bulletin_told_before.py` (look at how `tests/unit/test_bulletin_builder.py` and
`tests/unit/test_bulletin_daily.py` set up stored digests and bulletins and reuse their helpers or
fixtures where they are importable; otherwise copy the minimum).

Problem: `_split_shown` drops candidates whose URL or `cluster_key(title)` was in a ready bulletin of
the last `REPEAT_DAYS` days; only the `assessed` count shows it, nobody can see which story was left
out and why. Also an empty `cluster_key` (title with no key characters) matches any stored story
with an empty key.

Rules:
- `DayInput` gets `told_before: tuple[ToldBefore, ...] = ()`. `ToldBefore` is a new frozen dataclass
  in `builder.py` with `title: str`, `match: str` (`"url"` or `"title"`), `published_day: str`
  (ISO day of the stored bulletin that had it; the latest such day when several).
- `_recent_story_keys` (or its replacement) maps each URL and each non-empty title key to the latest
  stored day. `_split_shown` returns the kept candidates, the digest left-out count (unchanged) and
  one `ToldBefore` per left-out candidate (`match="url"` when the URL matched, else `"title"`), in
  candidate order.
- An empty title key is never stored and never matches (URL match still works).
- `prepare_from_input` puts `numbers["told_before"] = [{"title", "match", "published_day"}, ...]`
  (always present, `[]` when nothing was left out) next to `assessed` and `digest_articles`; the
  `no_digest` numbers stay as they are. Do not add it to the `bulletin_assessed_share` log event
  (keep that log line as is: build the log kwargs from the two counts only).
- Doc: say this in `builder.md` (R1) and in `daily.md` (numbers), with test names.

Tests:
- `test_told_before_records_url_match` (a candidate whose URL was in yesterday's stored bulletin:
  left out, `ToldBefore(title, "url", "<yesterday>")`),
- `test_told_before_records_title_match`,
- `test_empty_title_key_does_not_match`,
- `test_numbers_list_told_before` (through `prepare_from_input`).

## Fix 3. The writer journal cannot be opened: store the title-only bulletin

Files: `src/app/usecases/bulletin/daily.py` (`write_prepared`), `src/app/usecases/bulletin/daily.md`,
tests in `tests/unit/test_bulletin_daily.py`.

Problem: `write_prepared` enters `opener(...)` without a guard; when the journal cannot be opened
(`OSError`, `sqlite3.Error`, `ValueError`, the same set `_repeat_check` catches) the exception stops
`run_daily` before `save`, and the day is lost.

Rule: when the opener raises one of those, log it with `env.logger.exception("bulletin_writer_journal_failed")`,
then run `write_bulletin(prepared.bulletin, prepared.texts, ask)` with an `ask` that returns
`(None, JOURNAL_UNAVAILABLE)` (so the normal fallback runs: non-English titles removed, title-only
text), set `summary["cost_usd"] = 0.0`, and continue exactly like the normal path (bulletin,
`numbers["writer"]`, `bulletin_writer` log). `run_daily` then stores the bulletin. Doc: daily.md
Behavior with test names; also change the Invariant / note in `src/app/core/bulletin/repeats.md`
only if it mentions this gap.

Tests:
- `test_write_prepared_survives_a_journal_that_cannot_open` (writer_factory raises `OSError` on
  enter; result: `numbers["writer"]["reason"] == "journal_unavailable"`, bulletin kept, no raise),
- `test_run_daily_stores_the_day_when_the_writer_journal_fails` (the row is saved, status ready).

## Fix 4. Stale line in daily.md

`src/app/usecases/bulletin/daily.md` line 90 says `bulletin_home_page` and `bulletin_post_channels`
"default off and have no consumer yet". `bulletin_home_page` is read by
`src/app/web/routes/pages.py` (`_home_response`: `/` serves the bulletin when on). Check
`bulletin_post_channels` with `git grep -n bulletin_post_channels -- src` (no `head`) and write what
is true for each: the consumer of `bulletin_home_page` and whether `bulletin_post_channels` has one.

## Fix 5. Guard against a wrong model repeat (R2)

Files: `src/app/core/bulletin/repeats.py`, `src/app/core/bulletin/repeats.md`, tests in
`tests/unit/test_bulletin_repeats.py`.

Problem (real case, night of 2026-11-15): the model said candidate "South Korea probes top exam
scorer after AI cheating confession" repeats published "Google smartglasses from Gentle Monster and
Warby Parker open for preorder" (original "Google pushes privacy angle as Gemini-powered smartglasses
debut starting at $395"). The code applied it; the story was lost.

Rule: a repeat pair from the model is applied only when the candidate title shares at least one
word with the published story's shown title or its original title. A word is a run of `\w`
characters, compared casefolded, of at least `REPEAT_MIN_WORD = 5` characters (new constant). A
pair without a shared word is not applied: the candidate stays (it can still be merged by
`same_event`), and the summary gets `kept`: a list of `{"title", "published_day",
"published_title", "reason": "no_shared_word"}` (always present, `[]` when none). This is a cheap
guard, not a full check: true cross-language repeats with no common word are kept too (consistent
with the decision "a missed repeat is cheaper than a lost story"; add a Decisions line "decided
2026-11-16 (agent): ..."). `REPEATS_VERSION` stays (it names the prompt, which does not change).

Tests:
- `test_repeat_without_a_shared_word_is_kept` (use the real titles above),
- `test_repeat_with_a_shared_word_is_dropped` (e.g. "OpenAI launches ChatGPT Wallet" vs
  candidate "ChatGPT Wallet lets agents buy things"),
- `test_shared_word_may_come_from_the_original_title`,
- update the existing summary tests for the new `kept` key.

## Checks before you finish

1. `cd` to the worktree; `export PYTHONPATH=src`.
2. `set -o pipefail; /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q tests/unit/test_bulletin_*.py tests/unit/test_web_bulletin_page.py tests/unit/test_layer_imports.py tests/unit/test_monkeypatch_targets.py tests/unit/test_code_docs.py`
3. `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python -m ruff check src tests`
4. `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python -m pylint` on the changed src and
   test files (with `PYTHONPATH=src`).
5. `~/tools/unclebob/crapper/crapper <changed src files>` (every function under 10) and
   `~/tools/unclebob/dryer/dryer --threshold 0.8 <changed src files>`; if a tool prints nothing or
   fails, say so plainly.

## Final message (you cannot write report files)

Return as your final message: per fix, what changed (files, functions), the test names and that
each failed first (with the failure reason seen), the outputs (last lines) of every check above,
crapper and dryer results, and anything you could not do or decided yourself.
