# Prompt (Claude agent, Sonnet): spec 018 F11, reserve stories for the bulletin writer (2026-11-15)

Worktree (work only here): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/writer-reserve`,
branch `feat/018-writer-reserve`. Do not commit, push or use gh. No network, no ssh, no paid calls
(tests use fakes). Do not spawn sub-agents. Read `AGENTS.md` first (TDD, feature docs, exceptions).

Commands (from the worktree root; `V=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin`):
- tests: `PYTHONPATH=src $V/pytest -q -o addopts= <files>`
- lint at the end: `PYTHONPATH=src make lint PYTHON=$V/python`; docs: `$V/python scripts/check_code_docs.py`

## Why

The writer removes a world story in another language when its English headline or Telegram text
fails the checks (`_remove_non_english_stories` in `src/app/core/bulletin/writer.py`). Nothing
replaces it. Rebuilds of 2026-11-12 and 2026-11-13 on v0.1.179: the builder gave 7 and 8 stories,
4 and 5 were removed after the writer, 3 were published. The owner approved a bigger writer packet
(2026-11-15): the writer also gets reserve stories, and a removed Key results story is replaced by
a reserve story that passed the checks. Still one model call.

## Read first

`src/app/core/bulletin/builder.py` and `builder.md` (`build_bulletin`, `_key_results`, `Bulletin`,
`as_dict`), `writer.py` and `writer.md` (`all_stories`, `build_packet`, `WRITER_PROMPT`,
`parse_writer`, `_apply`, `_remove_non_english_stories`, `_needs_english_text`, `_summary`,
`_fallback`, `WRITER_MAX_OUTPUT`), `src/app/storage/bulletin_texts.py` (`load_sources`),
`src/app/usecases/bulletin/writer_run.py` (`_reservation`: the cost reservation grows with the
request size and `max_tokens`).

## Rules to implement (docs first, then a failing test for each rule, then code)

B1, builder. `Bulletin.reserve`: the next `RESERVE_MAX` (constant 4) stories after the Key
results selection, in the same rank order and from the same pool that `_key_results` selects from
(the same eligibility rules; a story already in Key results, the rubric, Cooperation or the
incident story is never in the reserve). The reserve is not part of the stored payload or of any
rendered page or text: `as_dict` and `render_text` leave it out, the builder's headline, numbers
and reactions ignore it. Fewer eligible stories give a shorter or empty reserve.

W1, packet. `build_packet` lists the reserve stories after the shown ones with the following ids
(shown `s1..sN`, reserve `sN+1..`), each reserve entry marked `"reserve": true`.
`load_sources` loads their texts too. The prompt (new `WRITER_VERSION` `bulletin-writer-7`) says:
write reserve stories exactly like the others; the headline of the day must not be about a
reserve story. The headline of the day is checked against the texts of the non-reserve stories
only.

W2, promotion, after the checks and after `_remove_non_english_stories`. While Key results has
fewer stories than the builder gave it, the next reserve story in order is appended to Key
results if it has a checked model headline and at least one checked site sentence, and (for a
known non-English world story) also passes `_needs_english_text` as not needing removal. A
reserve story that does not qualify is skipped. Other sections are never refilled. After
promotion `reserve` is empty in the result. Without a usable model answer (`_fallback`) nothing
is promoted and the reserve is dropped.

W3, summary. `summary["reserve"] = {"offered": <count>, "promoted": [<packet ids>]}`; the
existing counts (`stories_model`, `stories_title`) describe the final shown stories; `dropped`
keeps the packet ids, including those of reserve stories.

Money: say in your report whether `WRITER_MAX_OUTPUT` had to grow for up to 4 more stories and
by how much, and what `_reservation` gives for the fixture packet before and after. Do not change
`WRITER_MAX_USD_PER_DAY`.

## Tests

Builder (`tests/unit/test_bulletin_builder.py`, already over 1000 lines: put new tests in a new
file `tests/unit/test_bulletin_reserve.py`; copy only the small helpers you need): reserve order
and size, no overlap with shown stories, absent from `as_dict` and `render_text`.
Writer (same new file or `tests/unit/test_bulletin_writer_reserve.py`; keep every test file under
1000 lines): reserve ids and flag in the packet; a removed Key results story is replaced by the
first qualifying reserve story; a reserve story without a checked headline or site sentence is
skipped; a non-English reserve story needs headline and Telegram text; no promotion when nothing
was removed; no promotion on `_fallback`; the day headline grounded only in a reserve story is
dropped; the summary fields. Existing tests that pin the prompt version or packet shape are
updated to the new behavior.
Daily/store: run `tests/unit/test_bulletin_daily.py`, `test_bulletin_store.py`,
`test_web_bulletin_page.py`, `test_bulletin_repeats.py` and fix what the change breaks (the stored
payload must not gain a `reserve` key).

Every new test is seen failing for the expected reason before its code, the wiring tests too.

## End checks, once each, in this order

All `tests/unit/test_bulletin_*.py`, `tests/unit/test_web_bulletin_page.py`,
`tests/unit/test_code_docs.py`; `make lint`; then
`export PYTHONPATH=src PATH=$V:$PATH PIP_NO_INDEX=1`,
`~/tools/unclebob/crapper/crapper --coverage-command "$V/pytest -q -o addopts= tests/unit/test_bulletin_reserve.py tests/unit/test_bulletin_writer.py tests/unit/test_bulletin_builder.py" <changed src files>`
(CRAP under 10; if the flag differs, read `crapper --help`),
`~/tools/unclebob/dryer/dryer --threshold 0.8 <changed src files>`,
`~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "$V/pytest -q -o addopts= <the new test file(s)> tests/unit/test_bulletin_writer.py" src/app/core/bulletin/writer.py`
(kill survivors in the lines you changed with tests or give the reason; survivors in lines you did
not touch are only listed). Do not run the full suite: CI does.

## Final message (brief)

Files changed; each rule with its tests; the last lines of each end check; the money numbers
asked above; every decision you made that this prompt did not state (one line each); anything not
done and why.
