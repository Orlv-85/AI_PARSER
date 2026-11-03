# Prompt (Codex, gpt-6.1-sol high): spec 018 writer, paragraph split and short gloss (2026-11-03)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`fix/018-writer-sentences`, checked out from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/writer-sentences`. Do not touch any
other directory. Do not run git commit, push or any gh command. No network, no paid calls (tests
use fakes; never call DeepSeek). Do not spawn a doc review or any sub-agent: a separate reviewer
(another model) reviews after you.

Speed rule: while working run only `tests/unit/test_bulletin_writer.py` and `ruff` on changed files;
at the end run the full suite, `make lint`, crapper and mutator once each, in that order; run the
full suite again after the last test you add.

## The problem (production, first real bulletin, 2026-11-02, owner yes to fix 2026-11-03)

The writer prompt asks per story `site: 3 to 6 sentences`, but DeepSeek returned `site` as a list
with ONE string: the whole paragraph (113, 116, 151 words for the first three stories). `_sentences`
checks each list item as one sentence with `low=3, high=80` words, so every site paragraph was
dropped (`s1:site:1:word_count` ... `s7:site:1:word_count`); the preview page showed headlines only.
Glosses came at 15-20 words ("Amazon Bedrock: a fully managed AWS service that makes foundation
models available through a single API") against `GLOSS_MAX_WORDS` 14: dropped as `gloss:word_count`.
Real answer shape, first story (use it, shortened if you like, in a test):
`"site": ["Circle K built an automated triage system on Amazon Bedrock to investigate incidents and deliver structured summaries to Slack within minutes of an alert. The company operates more than 17,200 convenience and fuel retail stores across 27 countries, with point-of-sale, loyalty and electric vehicle ch..."]`

## Decisions (put them in `writer.md` Decisions as "decided 2026-11-03 (agent)")

- Split in code: each `site` and `telegram` list item is split into sentences before the checks;
  every resulting sentence then goes through the same word-count and grounding checks one by one
  (so one bad sentence drops alone, never the paragraph). The cap (`SITE_SENTENCES_MAX`,
  `TELEGRAM_SENTENCES_MAX`) applies to the sentences after splitting, in order. Drop codes keep the
  shape `<sid>:site:<n>:<code>` with `n` the sentence number after splitting (1-based, across items).
- Sentence splitter (new small pure function in `writer.py` or `writer_grounding.py`): a sentence
  ends at `.`, `!` or `?` (optionally followed by a closing quote or parenthesis) followed by
  whitespace and then an uppercase letter, a digit or an opening quote. It does not split inside
  numbers (`$5.55`, `17,200`, `3.5%`), after single capital initials (`J. Smith`, `U.S.`), or after
  common abbreviations (at least `Mr Mrs Ms Dr Prof Inc Ltd Co Corp vs etc e.g i.e St Jr Sr No`).
  Whitespace is normalized; empty pieces are dropped. ASCII only in code.
- Prompt: make the shape explicit: `site` is a JSON array of 3 to 6 strings, one sentence per
  string; `telegram` a JSON array of 1 to 2 strings, one sentence per string; `gloss` at most 12
  words. `GLOSS_MAX_WORDS` stays 14 (margin over the prompt). Changing the prompt text changes
  `WRITER_VERSION` (`bulletin-writer-2` -> `bulletin-writer-3`); follow how the doc and
  `test_prompt_pins_its_rules` pin it.
- Nothing else changes: no extra model call, same caps and journal, same fallbacks, same grounding
  order.

## Steps (doc first, then failing tests, then code)

1. Read `AGENTS.md` ("Feature Docs Next To Code", "Code Changes"), `src/app/core/bulletin/writer.md`,
   `writer.py`, `writer_grounding.py`, `specs/018-daily-inference/voice.md`, and
   `tests/unit/test_bulletin_writer.py`.
2. Doc `writer.md`: Behavior rules for the split, the cap after splitting, the drop code numbering,
   the prompt shape and gloss length; Decisions above; each rule names its tests.
3. Failing tests first (run them, see each fail for the expected reason), at least:
   - `test_site_paragraph_is_split_into_sentences` (the real one-item paragraph: kept sentences,
     each checked; `text_origin` model; no `site:1:word_count`)
   - `test_split_sentence_dropped_alone` (one ungrounded sentence inside a paragraph is dropped with
     its sentence number; the others stay)
   - `test_cap_applies_after_split` (a paragraph of 8 sentences keeps `SITE_SENTENCES_MAX`, logs
     `over_limit`)
   - `test_sentence_splitter_edges` (parametrized: numbers, `U.S.`, initials, abbreviations, `?`/`!`,
     closing quotes, a single sentence, extra whitespace)
   - `test_telegram_paragraph_is_split`
   - prompt pin updated for the new wording and `WRITER_VERSION`.
4. Code, smallest change in the current style; functions small (complexity under 10).
5. Final checks (once each, in this order; report last lines and exit codes):
   - `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto | tail -1`
   - `PYTHONPATH=src make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python 2>&1 | tail -5`
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/crapper/crapper src/app/core/bulletin/writer.py src/app/core/bulletin/writer_grounding.py`
     (report functions you wrote or changed with CRAP >= 8)
   - `env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_bulletin_writer.py" src/app/core/bulletin/writer.py`
     (kill survivors with tests or give a one-line reason each)
   - `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py; echo exit=$?` (alone, last)

## Report (your final message)

Files changed, one line each; failing-test output of step 3; outputs of step 5; mutator sites,
killed, survived, uncovered and what you did with survivors; anything you decided yourself or could
not do, one line each. Be brief.
