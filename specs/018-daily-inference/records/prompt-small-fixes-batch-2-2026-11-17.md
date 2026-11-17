# Prompt: spec 018 small fixes, batch 2 (2026-11-17)

Owner go 2026-11-17 ("да": three small things, then selection). One branch, one PR.

## Where and how

- Work only in the worktree `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-small-2` (branch
  `fix/018-small-batch-2`, from `origin/master`). Never touch `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
- Read `AGENTS.md`. Order per fix: feature doc first, then the failing test (run it, see it fail
  for the expected reason), then the smallest code. ASCII in code. Match the surrounding style.
- Python `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`; always
  `export PYTHONPATH=src` and `set -o pipefail`. Do not commit, push or open a PR.
- Keep test files under 1000 lines (`test_bulletin_writer.py` is about 980: do not add there).

## Fix 1. The repeat check: today's duplicates are not repeats (`src/app/core/bulletin/repeats.py`, `repeats.md`, `tests/unit/test_bulletin_repeats.py`)

Real case, night of 2026-11-16 (answer replayed from the prod journal): five articles of one
Korean exam story (c2, c8, c12, c15, c26) were rightly grouped in `same_event`, but c8, c12, c15,
c26 were also listed in `repeats` as repeating p1 ("Systematix says AI may deepen pricing pressure
on Indian IT services"), which has nothing to do with them; c2 was not. Same shape on 2026-11-15
(c16 -> p11). The model uses `repeats` for duplicates inside today.

Rules (write them in `repeats.md` with test names):
- Prompt: `REPEATS_PROMPT` says plainly that `repeats` is only for a candidate that tells the same
  event as a story in `published`, and that two of today's candidates about one event go only in
  `same_event`, never in `repeats`. `REPEATS_VERSION` becomes `bulletin-repeats-2`.
- Code guard: a repeat pair is not applied when its candidate is in a `same_event` group that has
  at least one member not listed in `repeats` (the model contradicts itself: if the event had been
  published, every member would be a repeat). Such pairs go to `summary["kept"]` with reason
  `same_event_conflict`; the shared-word guard (`no_shared_word`) stays and is checked as now.
  When every member of the group is listed in `repeats`, the pairs are applied as now.
- Update the summary rule (`kept` reasons) and add a Decisions line "decided 2026-11-17 (agent)".

Tests:
- `test_repeat_inside_a_partly_repeated_group_is_kept` (the real shape: group of five, four in
  `repeats` pointing to an unrelated p1 whose title shares a word so the word guard alone would
  not keep it; all four kept with `same_event_conflict`, the group merged into one event key),
- `test_fully_repeated_group_is_dropped` (every member in `repeats`: all dropped),
- `test_prompt_says_duplicates_of_today_are_not_repeats` (the prompt text and the version),
- update tests that pin `REPEATS_VERSION` or the prompt.

## Fix 2. Names that start with a lower-case letter (`src/app/core/bulletin/writer_grounding.py`, `writer.md` Grounding 5, `tests/unit/test_bulletin_writer_names.py`)

`grounding_error` (shared with the digest in `signals_brief.py`; do not change it) skips a word
that starts lower-case and has no digit, so "xAI", "iPhone", "eBay" are never checked (old gap,
named in `writer.md`).

Rule: in the writer's check only, a word that starts with a lower-case letter and has a capital
letter later (`[a-z]+[A-Z]` at its start, e.g. "xAI", "iPhone", "eBay", "macOS") is a name: its
stem (casefolded, possessive "'s" removed) must be among the evidence words (the same set the
other names use, `proof.words | SUBJECT_WORDS`); else `unsupported_name`. Run it after
`grounding_error` in `_evidence_error`. Remove the "old gap" sentence from `writer.md` and state
the rule with test names.

Tests: `test_camel_case_name_needs_the_text` ("xAI releases ..." dropped when the texts lack "xAI",
kept when they have it; "iPhone" the same), `test_lower_case_words_are_not_names` (an ordinary
sentence with only lower-case words is unchanged).

## Fix 3. Dead branch of the writer (`src/app/core/bulletin/writer.py`, `writer.md`, `tests/unit/test_bulletin_writer_language.py`)

Since v0.1.182 the builder never sets `headline_cut` (`builder.md` Headline), and the writer never
runs on stored bulletins, so the cut branch of `_title_is_day_headline` (the `made[1] and
bulletin.headline_cut ...` part) is unreachable. Remove it: a builder title headline equals
`make_headline(title)[0]` of a title that needs no cut. Update the tests in
`test_bulletin_writer_language.py` that build a cut headline by hand (around lines 31, 117-135)
so they keep testing the non-English title headline rule without a cut; keep `writer.md` true
(drop sentences about another story's cut headline). Do not touch `phrases.json` (`cut.marker`
stays: stored older headlines carry it) or the renderers.

## Checks before you finish

1. With `PYTHONPATH=src`: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:warnings tests/unit/test_bulletin_*.py tests/unit/test_web_bulletin_page.py tests/unit/test_layer_imports.py tests/unit/test_monkeypatch_targets.py tests/unit/test_code_docs.py`; print `rc=$?`.
2. `ruff check src tests`; `pylint` on changed src and test files.
3. `python -m coverage run --source=src/app -m pytest -q -p no:warnings tests/unit/test_bulletin_repeats.py tests/unit/test_bulletin_writer*.py tests/unit/test_bulletin_reserve.py`, `python -m coverage lcov -o target/coverage/python/lcov.info`, `~/tools/unclebob/crapper/crapper --changed --use-existing-coverage` (changed functions under 10), `~/tools/unclebob/dryer/dryer --threshold 0.8 --changed`.

## Final message (you cannot write report files)

Per fix: files and functions changed, each test name with the failure seen first, check outputs
with exit codes, and anything you decided yourself or could not do.
