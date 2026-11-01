# Report: spec 018 item 3, bulletin writer with grounding (2026-11-01)

Implementer report (background agent, model sonnet), saved by the coordinator. PR #195, branch
`feat/018-bulletin-writer`. No paid calls (fakes and `httpx.MockTransport`).

## Files

Doc `src/app/core/bulletin/writer.md` (registered); `builder.md`, `signals.md` updated. New:
`writer.py` (prompt, packet, parsing, `write_bulletin`), `writer_grounding.py`, `writer_run.py`
(journal and call), `src/app/storage/bulletin_texts.py` (archive text per link). Changed:
`signals_brief.py` (`grounding_error` extracted from `_sentence`, shared; daily brief unchanged, 43
tests pass), `builder.py` (fields on `Story`, `Bulletin`), `render.py` (Telegram note replaces the
title when present), `cli/main.py`. Tests `test_bulletin_writer.py` (41) and fixtures
`tests/fixtures/bulletin_writer/`.

## Checks (implementer)

ruff clean; `make lint` (mypy 264 files, pylint 10.00); full pytest 1904 passed, 1 skipped;
`check_code_docs.py --strict` exit 0; dryer none; crapper max 8.

## Cost (estimate)

8 stories x about 6,000 characters: about 13k input and 2k output tokens, about $0.006 a day
(about $0.2 a month); worst-case reservation about $0.02 per call against the $0.10 cap.

## Grounding

Catches: invented numbers and names (the `parse_brief` check against that story's texts, accents
removed, separators unified, Cyrillic transliterated); quotes not in the source or longer than 12
words; runs of 10+ words copied; never-list words and "the Administration"; markup; Cyrillic or CJK
letters in output. Cannot catch: wrong meaning, attribution, causes, tone, harm framing (prompt and
FR-022 review); non-Latin names other than Cyrillic without a Latin spelling (dropped); differing
transliterations (dropped); a number borrowed from another article of the same story.

## Real run command

`DS_API_KEY=... ai-news bulletin build --date 2026-10-30 --dry-run --write [--json] [--max-usd 0.05]`;
journal `data/bulletin/writer/<today UTC>/journal-bulletin-writer-1.sqlite3`.

## Decided by the implementer

Grounding per story (no ids cited); gloss held to sentence rules; never-list applied to model text
as is; only DeepSeek flash (journal prices at flash rates); no correcting retry; `Story.text_origin`
(`model`/`title`) beside `Story.origin`; `--max-usd` a run limit; a story counts as model text when
one site or Telegram sentence passed; site note, story headline, gloss only in `--json`.

## Open point

The never-list will drop some true sentences ("third-party tools"); keep strict until the first
real day shows the drop rate.

## Fixes after review (commit 1429ed7)

Per-story grounding test (`test_grounding_is_per_story`); writer names by whole words via
`grounding_error(words=...)` (brief default unchanged, 43 brief tests pass); weekday and month names
must stand in the story text (`test_names_match_whole_words_and_dates_need_the_text`); `writer.md`
"Cannot catch" lists spelled-out numbers, single-quote quotes, wrong meaning/attribution;
`STORY_TEXT_MAX` pinned; copy check on story headline and gloss; prompt test pins "Never copy" and
the grounding sentence; `WRITER_VERSION` `bulletin-writer-2`; docs on `--max-usd` (UTC-day total) and
the failed-call block. Six mutations killed. Checks: `make lint` clean; full pytest 1908 passed;
`check_code_docs.py --strict` exit 0. Coordinator checked the brief diff (default path unchanged)
and CI, merged under the owner's blanket yes.
