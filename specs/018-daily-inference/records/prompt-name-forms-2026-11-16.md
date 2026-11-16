# Prompt: translated name forms for the writer's name check (2026-11-16)

Owner go 2026-11-16 ("да"): teach the name check translations instead of freeing names. Read the
diagnosis first: `specs/018-daily-inference/records/report-name-check-diagnosis-2026-11-16.md`.

## Where and how

- Work only in the worktree `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-name-forms` (branch
  `feat/018-name-forms`, from `origin/master`). Never touch `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
- Read `AGENTS.md`. Order: doc first (`src/app/core/bulletin/writer.md`), then each failing test
  (run it, see it fail for the expected reason), then the smallest code. ASCII in Python code
  (the JSON data file holds non-ASCII forms; write them as real characters, UTF-8). Match the
  style of `writer_grounding.py` and `phrases.py`.
- Python `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`; in the worktree always
  `export PYTHONPATH=src` and `set -o pipefail`. Do not commit, push or open a PR.
- Put new tests in `tests/unit/test_bulletin_writer_names.py` (39 lines now); keep every test file
  under 1000 lines.

## The rule (write it into writer.md Grounding, check 5, with test names)

A capitalised name in model text passes the name check when, besides today's rules, it is a key of
the name-forms table and one of its forms stands in the story's texts (the headline of the day: of
all non-reserve stories, as now). Everything else stays as it is: a name with no table entry, or
whose forms are all absent, is still dropped.

### Data: `src/app/core/bulletin/name_forms.json`

- Object: key = an English name word, lower case, one word (`"us"`, `"european"`, `"italian"`,
  `"parliament"`, `"november"`); value = list of forms in other languages (and English variants).
- Forms are written as they appear in sources (native script); the loader folds them with
  `fold(...).casefold()` (Cyrillic and, after this change, Greek become Latin).
- Matching of a folded form against the folded, casefolded evidence text:
  - a form that is ASCII after folding matches at a word start; a form ending in `*` is a prefix
    (`"ital*"` matches "italiane"), otherwise it must be the whole word or words (`"usa"` does not
    match "usage"; `"stati uniti"` matches the two words). Without `*` at least 3 characters, with
    `*` at least 4 before the `*`;
  - a form that still has non-ASCII letters after folding (Chinese, Arabic) matches as a substring.
- Content (curate carefully; a wrong form only lets a name pass when that form is in the source):
  - Countries, regions and their adjective / people words seen in the world stream: US (and
    "american"), America, China/Chinese, Russia/Russian, Ukraine/Ukrainian, Europe/European, EU,
    Italy/Italian, Greece/Greek, Spain/Spanish, Portugal/Portuguese, Brazil/Brazilian,
    France/French, Germany/German, Japan/Japanese, Korea/Korean, India/Indian, Vietnam/Vietnamese,
    Turkey/Turkish, Poland/Polish, Britain/British, UK, Canada/Canadian, Australia/Australian,
    Arab, Israel/Israeli, Iran/Iranian, Mexico/Mexican, Argentina/Argentine.
  - Institution words: Parliament, Ministry, Government, Commission, Council, Senate, Court,
    University, Police, Bank.
  - Months January..December and weekdays Monday..Sunday.
  - Languages of the forms: rus, ukr, spa, por, ita, fra, deu, ell, zho, vie, ara, plus English
    variants ("united states", "u.s", "american*" for "us"). Use stems with `*` for inflected
    languages (Russian "росси*", Italian "italian*", Greek "ελλην*").
  - Do not add person or company names; those must stand in the text as today.
- `pyproject.toml` `[tool.setuptools.package-data]`: add `"name_forms.json"` next to
  `"phrases.json"` (the image installs the package; without it the file is missing on prod).

### Code: `src/app/core/bulletin/writer_grounding.py`

- `NAME_FORMS_PATH`, a loader (cached once) that folds the forms and validates the table (raise
  `ValueError` with a clear message on: key not lower case or not one word, empty list, a form too
  short as above). A broken table must fail tests, not production.
- In `_evidence(raw)` (already cached per text) add the table keys whose forms stand in the text,
  and add each pair of adjacent tokens joined ("ha noi" gives "hanoi"); `_evidence_error` passes
  `proof.words | SUBJECT_WORDS` as now, where `proof.words` now holds those additions. Keep
  functions small (CRAP < 10).
- `fold`: transliterate Greek like Cyrillic (after accents are removed, so "έ" is "ε"): a TRANSLIT
  table for Greek letters, lower and upper, final sigma. "Κεραμέως" folds to "Kerameos". Keep the
  existing Cyrillic behavior.
- `HEADLINE_OPENERS`: add `Commentary Critics Analysts Hundreds Thousands Dozens`.

### Version

- `WRITER_VERSION` becomes `bulletin-writer-8` (writer.md: "`WRITER_VERSION` (prompt and checks)");
  update every pin of the version string in docs and tests.
- writer.md Decisions: rewrite the "decided 2026-11-15 (owner)" entry: on 2026-11-16 the owner chose
  to teach the check translations (name-forms table) because 17 of 22 headlines of stories in other
  languages failed on 2026-11-12..14; a name still must stand in the source in one of its forms.
  Add "decided 2026-11-16 (agent)" lines for joined words and Greek transliteration.

## Tests (each fails first)

- `test_translated_country_passes` ("US" with evidence "Stati Uniti"; "Italian" with
  "scuole italiane"; "European Parliament" with "Parlamento Europeo").
- `test_russian_and_greek_forms_pass` ("Russian" with "российских"; "Greek" with "ελληνικές").
- `test_cjk_and_arabic_forms_pass` ("China" with "中国"; one Arabic form).
- `test_month_form_passes` ("November" with "ноября" or "novembre").
- `test_name_without_its_form_still_fails` ("Italian" with a Spanish text that has no form;
  "Hong Kong" with Chinese text "港科大").
- `test_exact_form_is_a_whole_word` (a form without `*`, e.g. "usa", does not match "usage").
- `test_joined_words_ground_a_name` ("Hanoi" with "Ha Noi" in Vietnamese with accents: "Hà Nội").
- `test_greek_is_transliterated` ("Kerameos" with "Κεραμέως"; `fold` result).
- `test_new_openers_are_not_names` ("Commentary examines ...", "Critics say ...").
- `test_name_forms_table_is_valid` (the shipped table loads; the loader rejects a bad key and a
  too-short form, given a temp file).
- Update `test_names_in_a_foreign_story_still_need_the_text` if it asserts that "Hanoi" or
  "Italian" is dropped on evidence that now has a form; keep its intent with a name that has no
  form.

## Checks before you finish

1. From the worktree with `PYTHONPATH=src`: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:warnings tests/unit/test_bulletin_*.py tests/unit/test_web_bulletin_page.py tests/unit/test_layer_imports.py tests/unit/test_monkeypatch_targets.py tests/unit/test_code_docs.py tests/unit/test_deepseek_digest.py`, then print the exit code (`echo rc=$?`).
2. `ruff check src tests`; `pylint` on changed src and test files.
3. Coverage for crapper: `python -m coverage run --source=src/app -m pytest -q -p no:warnings tests/unit/test_bulletin_writer*.py`, `python -m coverage lcov -o target/coverage/python/lcov.info`, then `~/tools/unclebob/crapper/crapper --changed --use-existing-coverage` (changed functions under 10) and `~/tools/unclebob/dryer/dryer --threshold 0.8 --changed`.

## Final message (you cannot write report files)

Per part (data, code, version, docs): what changed; each test name and the failure seen first;
the table's key count and languages covered; the output tails of every check with the exit code;
anything you decided yourself or could not do.
