<!-- code-doc
module: src/app/core/bulletin/writer.py
covers:
  - src/app/core/bulletin/writer*.py
  - src/app/storage/bulletin_texts.py
-->
# Bulletin writer (bulletin, item 3)

One model call per day retells the stories that the builder selected (`src/app/core/bulletin/builder.md`) in the voice of
`specs/018-daily-inference/voice.md`: a headline of the day and, per story, a headline, a site note,
a Telegram note and a gloss. Every sentence is checked against the original texts before it is kept;
whatever fails falls back to the builder's title-only text. Spec: FR-005, FR-012, User Story 1
scenario 4, ER-1/2/3/6/8/9/11/12 in `specs/018-daily-inference/spec.md`. Storage is described in
`src/app/storage/bulletin_store.md`; the daily job is in `daily.md`, no page yet.
Entry: `ai-news bulletin build --date D
[--dry-run] --write`.

## Behavior

```mermaid
flowchart LR
  bulletin["Builder bulletin (titles)"] --> sources["Archive text per link, else title + summary"]
  sources --> packet["Packet: stories s1..sN, texts cut to STORY_TEXT_MAX"]
  packet --> call["One DeepSeek call through the writer journal"]
  call --> ok{"Answer usable?"}
  ok -- no --> fallback["Whole bulletin stays title-only, reason in the summary"]
  ok -- yes --> split["Split site and Telegram list items into sentences"]
  split --> check["Per sentence: markup, never-list, quotes, copying, numbers, names"]
  check --> drop["Failing sentence dropped"]
  drop --> story{"Story has sentences left?"}
  story -- no --> title["Story: title with outlet, origin title"]
  story -- yes --> model["Story: model text, origin model"]
  check --> headline{"Headline of the day passes?"}
  headline -- no --> builder["Builder's title headline"]
```

**Call**
- Input is the stories of the builder bulletin in order (Key results, rubric story, Cooperation, the
  "Among them" story) as ids `s1..sN`. Each story sends up to `ARTICLES_PER_STORY` of its links; an
  article with an archive text sends it, the rest of the story's budget `STORY_TEXT_MAX` shared
  between them (newest `source_page` text, else the newest text of any origin, cut at a word
  boundary); an article without text sends title and summary (`SUMMARY_MAX`). Tests:
  `test_packet_sends_text_or_title_and_summary`, `test_story_text_limit_is_pinned`, `test_loader_prefers_source_page_text`,
  `test_loader_falls_back_to_summary`, `test_packet_handles_missing_and_empty_sources`,
  `test_packet_shares_budget_only_between_articles_with_text`.
- One request per bulletin (FR-005): `WRITER_MODEL` (DeepSeek flash, prices of `BRIEF_PRICES`),
  temperature 0, JSON object, at most `WRITER_MAX_OUTPUT` tokens. A day with no stories makes no
  call. Tests: `test_request_body_is_one_json_call`, `test_no_stories_no_call`.
- The prompt is `WRITER_PROMPT`, versioned by `WRITER_VERSION`; it states the voice rules of
  `specs/018-daily-inference/voice.md` and the editorial rules ER-1/2/3/6/8/9/11/12. It explicitly asks
  for `site` as a JSON array of 3 to 6 strings and `telegram` as a JSON array of 1 to 2 strings,
  one sentence per string, and a gloss of at most 12 words. Validation keeps `GLOSS_MAX_WORDS`
  as a margin above the prompt. Changing the text changes the version (`bulletin-writer-3`).
  Tests: `test_prompt_pins_its_rules`.
- The call goes through the provider journal (`PilotJournal`, provider `deepseek`) of the real UTC
  day: one file `data/bulletin/writer/<UTC day>/journal-<WRITER_JOURNAL_VERSION>.sqlite3`, fixed cap
  `WRITER_MAX_USD_PER_DAY` (FR-012), whatever `--date` the run builds. A request with the same body
  on the same UTC day is replayed from the journal and costs nothing. `--max-usd` only lowers the
  limit: it caps the total writer spend of that UTC day (committed in the journal plus the
  reservation of the new call), checked before sending; above the daily cap it is rejected. A failed
  call (outage, HTTP error, unreadable usage) blocks further writer calls that UTC day with
  `unknown_or_failed_previous_call_requires_review` until the operator checks the journal file
  `data/bulletin/writer/<UTC day>/journal-<WRITER_JOURNAL_VERSION>.sqlite3` and the log line, then
  deletes that file after accepting the risk of paying that call twice (the cap then starts over for
  the day). An identical rerun after a good call is replayed free.
  Tests: `test_journal_is_one_file_per_utc_day_and_replays`, `test_run_limit_only_lowers`,
  `test_cap_reached_falls_back`, `test_cli_rejects_max_usd_above_the_cap`; the block after a failed call
  has no test of its own (the journal's rule, `test_transport_outage_falls_back` shows the outage).

**Failure** (the call never raises into callers)
- No answer (cap reached, run limit, outage, HTTP error, an unreviewed earlier call), a wrong model,
  a truncated answer (`finish_reason` not `stop`), invalid JSON or a wrong shape: the whole bulletin
  stays as the builder made it (story `text_origin` `title`), `writer_reason` of the bulletin and
  `reason` of the summary say why. Tests: `test_unavailable_model_falls_back_to_titles`,
  `test_invalid_answers_fall_back`, `test_transport_outage_falls_back`.

**Grounding** (User Story 1 scenario 4; the open limit of FR-022 stays: this catches invented names
and numbers, not distorted meaning). Applied to every model sentence, story headline, gloss and the
headline of the day, in this order; the first failing check names the drop reason (Tests:
`test_first_failing_check_names_the_reason`):
1. Shape and length: a string of `SENTENCE_MIN_CHARS`..`SENTENCE_MAX_CHARS`; no URL or markdown; no
   Cyrillic or CJK letters in the output (ER-12). Tests: `test_non_english_output_is_dropped`,
   `test_markup_is_dropped`, `test_short_and_long_sentences_are_dropped`.
2. Never-list (ER-4, ER-2): the words of `never_word` (`phrases.py`) and "the Administration" in
   model text. The Administration speaks only in fixed phrases (ER-6: framing adds no facts).
   Tests: `test_never_list_words_are_dropped`.
3. Quotes (ER-9, ER-3): text in double quotation marks must be an exact substring of the original
   (after folding) and at most `QUOTE_MAX_WORDS` words; so a quote that is not in the source, or a
   translated quote, is dropped. Tests: `test_long_quote_is_dropped`,
   `test_quote_must_be_in_the_source`, `test_quote_and_copy_edges`.
4. Copying (ER-9): a run of `COPY_RUN_WORDS` words that also stands in the original is dropped
   (sentences, story headlines and glosses; not the headline of the day). Tests: `test_copied_run_is_dropped`,
   `test_headline_and_gloss_are_checked_for_copying`, `test_quote_and_copy_edges`.
5. Numbers and names, the check of `parse_brief` (`grounding_error` in `signals_brief.py`) against
   the texts of that story: every number and every capitalised word or word with a digit must stand
   in the texts of the story's sources (the headline of the day: of all stories). Sentence
   starters are exempt (`WRITER_STARTERS`). A name must match a whole word of the texts ("Meta"
   does not pass on "metadata"); months and weekdays are names too and must stand in the texts of
   the story. Evidence is per story: a name or number found only in another story does not
   ground a sentence. Folding makes
   the comparison tolerant: accents are removed, decimal commas and thousand separators are
   unified, Cyrillic is transliterated, so an English sentence about a Russian article can name
   "OpenAI" when the text has "ОпенАИ". Tests: `test_grounded_sentences_are_kept`,
   `test_invented_number_is_dropped`, `test_invented_name_is_dropped`, `test_grounding_is_per_story`,
   `test_names_match_whole_words_and_dates_need_the_text`,
   `test_translation_case_grounds_names_by_transliteration`, `test_folding_unifies_accents_and_numbers`.

What it cannot check: meaning (a true name and number in a false claim: "Mozilla said ..." passes if
Mozilla and the numbers stand in the text), attribution ("Block says" versus a bare claim), causes
and effects, tone, and harm framing (ER-6, ER-11 stay with the prompt and the human review of
FR-022 on the first real days). Numbers spelled out in words ("twelve") are not checked. Quotes in
straight single quotes are not checked (the prompt asks for double quotes). The never-list also
drops true sentences ("third-party tools"). Names in non-Latin scripts other than Cyrillic (Chinese, Japanese, Arabic
and so on) can be checked only when the text also spells them in Latin letters; otherwise the
sentence is dropped. A Cyrillic transliteration that differs from the English spelling ("Yandeks")
drops the sentence. A first word that is a name and also a starter is not checked. False drops are
the safe direction: the story falls back to its title.

**Result**
- Each string in a `site` or `telegram` list is split before word-count and grounding checks.
  A boundary is `.`, `!` or `?`, optionally followed by closing quotes or parentheses, then
  whitespace and an uppercase letter, digit or opening quote. Numbers, single capital initials
  (including `U.S.`) and common abbreviations (`Mr Mrs Ms Dr Prof Inc Ltd Co Corp vs etc e.g i.e
  St Jr Sr No`) do not split. Whitespace is normalized and empty pieces are dropped. Tests:
  `test_sentence_splitter_edges`, `test_site_paragraph_is_split_into_sentences`,
  `test_telegram_paragraph_is_split`.
- A boundary inside an open double quotation is skipped. A quotation is open while the text up
  to the boundary, folded as the quote check folds it (every double quotation mark, straight,
  curly or low, becomes `"`), has an odd number of marks. A boundary that includes the closing
  quote can split; a quote that never closes keeps the rest as one piece. Quotes reach grounding whole, so splitting cannot bypass
  the quote check. Tests: `test_split_keeps_quotes_whole`, `test_splitter_quote_edges`,
  `test_sentence_splitter_edges`.
- Each resulting sentence is checked independently in the same order as before; one bad sentence
  drops alone. Drop codes keep `<sid>:site:<n>:<code>` (or `telegram`), with `n` the 1-based sentence
  number after splitting across all list items. Tests: `test_split_sentence_dropped_alone`,
  `test_split_sentences_keep_word_count_boundaries`.
- After splitting, a sentence list per story is cut in order to `SITE_SENTENCES_MAX` (site) and
  `TELEGRAM_SENTENCES_MAX` (Telegram) passing sentences; remaining sentences are counted in
  `over_limit`. There is no minimum. A story keeps model text when at least one
  site or Telegram sentence passed (`text_origin` `model`); the Telegram note falls back to the
  title when only the site note passed, and the other way round for the site. A failing story
  headline or gloss is dropped alone. Tests: `test_story_without_sentences_falls_back_to_title`,
  `test_sentence_caps`, `test_cap_applies_after_split`,
  `test_bad_story_headline_and_gloss_are_dropped_alone`.
- The headline of the day: at most `HEADLINE_MAX_WORDS` words (at least `HEADLINE_MIN_WORDS`),
  capitals, no cut marker; a failing one keeps the builder's headline (`headline_origin` `title`).
  Tests: `test_bad_headline_of_the_day_falls_back`.
- Fixed text is untouched: opening, numbers line, rubric name, reactions, closing. `render_text`
  shows the Telegram note instead of the title where a story has one (the reaction follows the note);
  the site note, story headline and gloss are in the JSON object. Tests:
  `test_render_uses_telegram_notes`, `test_fixture_bulletin`.

**Command** `ai-news bulletin build --date D [--dry-run] [--write] [--json] [--max-usd X]`
- Without `--write` the command makes no key read, no call and no journal; its rendered text is
  item 2's (`--json` also has `article_ids` per story, and a run without `--dry-run` stores the
  day, see `src/app/storage/bulletin_store.md`). Tests:
  `test_cli_without_write_makes_no_call`.
- `--write` needs `DS_API_KEY` (exit 2 without); it prints the bulletin with model text and, on
  stderr, one JSON line of the writer summary; with `--json` the object gains a `writer` key
  (`version`, `model`, `reason`, `stories_model`, `stories_title`, `headline_origin`, `dropped`,
  `cost_usd`). Storage is described in `src/app/storage/bulletin_store.md`. A skipped day makes no
  call. Tests: `test_cli_write_needs_the_key`, `test_cli_write_prints_the_bulletin_and_summary`,
  `test_cli_write_json`, `test_cli_write_outage_falls_back`, `test_cli_write_can_store`,
  `test_cli_write_skipped_day_makes_no_call`.

## Decisions

- decided 2026-11-03 (agent): split list items in code so a paragraph-shaped answer keeps its
  grounded sentences; apply the existing caps and numbered drops after splitting, in order.
- decided 2026-11-03 (agent): use a small pure punctuation splitter with initials and common
  abbreviation exceptions; it needs no extra model call or dependency.
- decided 2026-11-03 (agent): preserve open quotation spans during splitting so an invented
  multi-sentence quote cannot evade the existing quote check; open quotes are counted after the
  same folding the quote check uses, so every quotation mark it pairs is seen.
- decided 2026-11-03 (agent): the copy check stays per sentence, as when the model returns one
  sentence per list item; a copied run that crosses a sentence boundary is not checked. A
  cross-boundary check also flagged close paraphrases in adjacent sentences
  (`test_split_sentence_dropped_alone`, `test_cap_applies_after_split`).
- decided 2026-11-03 (agent): make the arrays and one-sentence strings explicit, ask for a gloss
  of at most 12 words with `GLOSS_MAX_WORDS` unchanged, and bump `WRITER_VERSION` to
  `bulletin-writer-3` because the prompt text changes; caps, journal, fallbacks and grounding order
  stay unchanged.
- The core takes an `ask` function and plain data and imports no I/O module; the journal and the
  HTTP client are `writer_run.py`. A test pins the import list.
- Grounding reuses `grounding_error`, cut out of `parse_brief`'s `_sentence` so the two checks cannot
  drift; the daily brief's behavior is unchanged (its tests pass as they were).
- Evidence for a story is exactly what the model was sent (cut texts, titles, summaries, outlet
  names), not the full archive text: what it could not see it cannot ground.
- One story-level evidence instead of per-sentence citations: the model cites no ids; a sentence is
  grounded if its names and numbers stand anywhere in its story's sources (decided 2026-11-01
  (agent): fewer output tokens; the cost is that a sentence may borrow a number from another
  article of the same story).
- A gloss is held to the same rules as a sentence, so it can only restate what the article says
  about a name; background knowledge is not published (decided 2026-11-01 (agent): ER-1).
- The never-list is applied to model text as it stands, so "third party", "market leader" and
  "government" in a retold story drop the sentence; the prompt tells the model to write around them
  (decided 2026-11-01 (agent): the prompt of this item names the check; loosening it is an owner
  call after the first real day).
- The journal is the world stream's shape: the day is the real UTC day and the cap is fixed
  (`WRITER_MAX_USD_PER_DAY`); lowering the cap by `--max-usd` is a run limit, not a new journal
  identity, because another cap value would open another file and add up to several caps.
- Model `WRITER_MODEL` only: `PilotJournal` prices every answer at the flash rates, so another
  model would be billed wrongly in the journal. Pro needs per-model prices there first.
- `Story.text_origin` is new beside `Story.origin`: `origin` (`digest`, `world`) says where the
  story came from; `text_origin` (`model`, `title`) says who wrote its text (FR-007).
- The Telegram text of a story is the note without a headline; the site note and headline are for
  the page (item 4+) (voice.md samples).
- One attempt, no correcting retry (FR-005 says one call); the transport retry of the journal is
  the only second send and is reserved against the cap.

## Invariants

- One request per bulletin build; none for a skipped day, an empty bulletin or without `--write`.
- Never more than `WRITER_MAX_USD_PER_DAY` committed per real UTC day.
- No model sentence in a bulletin that did not pass every check of Grounding.
- A failure of the model or the journal returns a complete title-only bulletin, never an exception.
- The builder's fixed phrases, links, sections and counts are unchanged by the writer.

## Code map

| Where | What |
| --- | --- |
| `src/app/core/bulletin/writer.py` | constants, `WRITER_PROMPT`, `SourceText`, packet, `split_sentences`, `parse_writer`, `write_bulletin` |
| `src/app/core/bulletin/writer_grounding.py` | folding, `sentence_error`: the checks of Grounding |
| `src/app/core/bulletin/writer_run.py` | `open_writer`: writer journal, client, `ask` |
| `src/app/storage/bulletin_texts.py` | `load_sources`: archive text, summary and title per link |
| `src/app/core/daily/signals_brief.py` | `grounding_error` (shared), `request_body`, `request_key`, `BRIEF_PRICES` |
| `src/app/core/bulletin/builder.py` | `Story` and `Bulletin` fields of the writer |
| `src/app/core/bulletin/render.py` | Telegram note in the text |
| `src/app/cli/main.py` | `bulletin build --write` |

Versions: `WRITER_VERSION` (prompt and checks), `WRITER_JOURNAL_VERSION` (journal identity).

## Tests

`tests/unit/test_bulletin_writer.py` on the fixtures in `tests/fixtures/bulletin_writer/` (a
hand-written day: source texts and one model answer, marked as fixture, not a recording).
