# Writer F9 and F1 report (2026-11-09)

Worktree: `docs/work/worktrees/writer-f9-f1`, branch `fix/018-writer-f9-f1`.
Task: `prompt-writer-f9-f1-codex-2026-11-09.md`. No commit, push, gh command,
network request, paid call or sub-agent was used.

## Files changed

- `src/app/core/bulletin/builder.md`: title-language propagation contract.
- `src/app/core/bulletin/builder.py`: additive `Candidate.language` and
  `Story.language`, default `unknown`; the representative supplies the title language.
- `src/app/storage/bulletin_input.py`: pass the stored world candidate language.
- `src/app/core/bulletin/writer.md`: F9 behavior, F1 prompt rule and writer version.
- `src/app/core/bulletin/writer.py`: filter after checks and on title-only failure;
  clear a removed title's day headline; actual-speaker prompt; writer version 5.
- `src/app/storage/bulletin_store.md`: additive payload key and old-payload default.
- `tests/unit/test_bulletin_builder.py`: input, representative and old-payload tests.
- `tests/unit/test_bulletin_writer.py`: prompt rule/version test and optional
  builder input for the existing fake writer helper.
- `tests/unit/test_bulletin_writer_language.py`: channel requirements, sections,
  fallback, summary and headline tests, sharing the existing hand-written fixtures.
- This report.

## Implemented rules and decisions

Known non-English means a world story with language outside `unknown`, `eng`, and
empty. Such a story survives only when its model headline and at least one Telegram
sentence pass the existing writer checks. A passing site sentence alone is not
enough; site text is not required when the headline and Telegram sentence pass.
Removal applies to Key results, rubric, Cooperation and the incident story, both
after a usable answer and after an unavailable or invalid answer. A missing story
entry is handled by the same rule. Digest stories retain their existing fallback.

The summary appends `<sid>:story:non_english_title` using the original packet ids
and order; model/title summary counts describe retained stories. `incidents` and
the builder input object are unchanged. `Bulletin.as_dict()` includes language.
Constructing `Story` from an old payload without the key defaults to `unknown`;
stored JSON is not migrated or rewritten.

If a removed title supplied the builder's day headline, the headline becomes
`None` and `headline_cut` becomes false, including for a clause-cut title. This
uses the builder's existing no-headline behavior. An unrelated title headline,
a missing headline and a passing model day headline retain their existing behavior.

F1 asks for the actual source speaker for each statement. An outlet's comparison,
context or judgement stays attributed to that outlet (the prompt gives
"TechCrunch notes ..."), with no speaker only for plain facts in the source.
`WRITER_VERSION` is `bulletin-writer-5`; journal identity and limits are unchanged.
Attribution remains a prompt rule, not a semantic validator.

- Decided 2026-11-09 (agent), as required by the task: drop rather than translate
  a non-English title; a translation would be unchecked model text.
- Found in `gdelt.py::parse_gkg_line`: English GDELT rows lack the translation
  language field and use `LANGUAGE_UNKNOWN`; translated rows retain their code.
- Decided 2026-11-09 (agent): match a removed builder headline with `make_headline`,
  including its cut flag and trailing punctuation marker, without adding a
  phrase-library read to the pure writer. A title prefix alone is insufficient.

## Test-first evidence

Docs were edited before tests, and tests ran before source changes. Initial selected
run: **29 failed, 9 passed, 252 deselected**. Five initially passing positive/fallback
cases were strengthened to assert serialized language and rerun before source
changes: **5 failed, 142 deselected**, all with `KeyError: 'language'`.

| Test | First failure before implementation |
| --- | --- |
| `test_world_story_language_reaches_story` (6 cases) | `Candidate` had no `language`. |
| `test_story_language_is_the_representatives` | `Candidate` rejected the `language` argument. |
| `test_old_payload_without_language_reads_unknown` | `Story` had no `language`. |
| `test_non_english_story_without_headline_is_removed` (2 cases) | Foreign-title story remained after missing/rejected headline. |
| `test_non_english_story_without_telegram_is_removed` (2 cases) | Foreign-title story remained after empty/rejected Telegram note. |
| `test_non_english_story_with_model_text_stays` | Existing text behavior passed; strengthened payload assertion failed with missing language key. |
| `test_unknown_or_english_language_story_falls_back_to_title` (4 cases) | Existing fallback behavior passed; strengthened payload assertion failed with missing language key. |
| `test_title_only_bulletin_removes_non_english_stories` (8 cases) | All stories remained after unavailable/invalid answer, in each section. |
| `test_removed_story_is_in_dropped` (4 cases) | Only the rejected-headline reason appeared; story-removal reason was absent. |
| `test_day_headline_not_from_removed_story` (8 cases) | Four cases failed on the retained foreign title/cut title; unrelated/missing headline cases already passed. |
| Extended `test_prompt_pins_its_rules` | Version remained `bulletin-writer-4` instead of 5. |

Two supplemental regression tests were added after the first green feature run;
they passed on first run (no claim of a red run):
`test_missing_writer_entries_remove_world_stories_in_original_order` and
`test_removed_title_without_headline_boundary_keeps_other_day_headline`.

Mutation follow-up added `test_removed_title_prefix_does_not_clear_another_cut_headline`
(three cases). The short-title case killed the two original guard survivors. Extending
it to a removed clause-cut title first produced **1 failed, 1 passed**: the prefix
match wrongly cleared a longer retained story's cut day headline. The smallest fix
replaced `startswith` with an anchored match of the complete made headline plus a
punctuation marker. The final cases also distinguish a short removed title from
another story's longer title cut to the same words.

Feature validation: **379 passed, 1 warning** across builder, writer, store, daily
and web bulletin tests. Scoped Ruff on the three changed source files and two
changed test files passed after fixing two test line-length findings.

## Final validation

Commands run from the worktree with `PYTHONPATH=src`, the main repository venv on
PATH, `PIP_NO_INDEX=1` and `PYTHONDONTWRITEBYTECODE=1`. Logs are under the ignored
`target/writer-f9-f1/` directory. Final checks are recorded below in execution order.

1. Full suite: **2474 passed, 3 skipped, 6 warnings**, 149.54 seconds; exit 0.
   Command: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts=`.
   The skips are PostgreSQL integration tests without `AINEWS_TEST_POSTGRES_URL`.
   Warnings are the existing Starlette httpx and SQLite date-adapter deprecations.
2. `make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`:
   Ruff passed; mypy passed (279 source files). Pylint found only
   `too-many-lines` in the expanded writer test file (1108/1000). The F9 cases
   were then moved unchanged into `test_bulletin_writer_language.py`.
   Only the failed `make lint-pylint` component was rerun, per the speed rule.
   Rerun: exit 0, **10.00/10**. Scoped Ruff on both writer test files after
   the move also passed. A later one-line headline-matching correction was checked
   with scoped writer tests and mutation follow-ups, as detailed below; the full
   suite and broad lint were not repeated, per the speed rule.
3. `python scripts/check_code_docs.py --diff origin/master --strict`: **15
   checked, ok**, exit 0. No fallback invocation without `--diff` was needed.
   The script checks names in the working tree, but its Git range is
   `origin/master...HEAD` and therefore excludes these uncommitted edits.
   Manual inspection confirms matching builder/writer docs for all three changed
   covered source files. `git diff --check` also passed.
4. CRAP: exit 0; **all analyzed functions below 10**, maximum 9.0 in the
   existing `build_bulletin`. New helpers: `_needs_english_text` 4.0,
   `_title_is_day_headline` 6.0, `_clear_removed_headline` 3.0,
   `_remove_non_english_stories` 7.0; all have 100% measured coverage.
   Changed `story` 3.0, `_world_candidates` 5.0, `_fallback` 1.0 and
   `write_bulletin` 5.0 also have 100% measured coverage.
   To honor the single full-suite run, crapper used `--coverage-command` with
   the six feature test files and pytest-cov's LCOV output at
   `target/coverage/python/lcov.info`: **379 passed, 80 warnings** in 8.50s.
   The coverage run additionally exposed ResourceWarnings from existing unclosed
   SQLite test engines; these did not fail tests. Metrics: `.metrics/crap.edn`.
5. Dryer `--threshold 0.8` on the three changed source files: exit 0,
   **no duplicate candidates found**. Metrics: `.metrics/dry.edn`.

6. Mutator used existing LCOV, four workers, and the builder, writer and
   writer-language feature test files. Initial complete pass across all three
   changed source files: **148 killed, 10 survived, 6 uncovered, 164 sites**,
   exit 3 (survivors). No live providers were used.

   Scoped follow-ups killed both new headline guard survivors, reproduced and
   corrected the cut-title-prefix bug, and checked the resulting helper again.
   The new string-concatenation mutation is killed too. A subsequent scoped pass
   restores outcomes for unchanged later functions whose byte-offset mutation ids
   shifted after that one-line edit. No full mutation sweep was repeated.

   Final recorded totals: **151 killed, 8 survived, 6 uncovered, 165 sites**
   (95.0% of executed mutations killed). All new-code mutation sites are killed;
   the headline helper has **10 killed, 0 survived, 0 uncovered**. The eight
   retained survivors keep the aggregate tool exit status at 3; this is not an
   all-green mutation result.

   | Source file | Killed | Survived | Uncovered | Sites |
   | --- | ---: | ---: | ---: | ---: |
   | `src/app/core/bulletin/builder.py` | 55 | 7 | 1 | 63 |
   | `src/app/core/bulletin/writer.py` | 69 | 1 | 2 | 72 |
   | `src/app/storage/bulletin_input.py` | 27 | 0 | 3 | 30 |

   Final scoped writer-language tests: **34 passed, 1 warning**, 0.57 seconds.
   Scoped Ruff on the final writer source and language tests passed. The final
   `git diff --check` passed.

### Remaining mutation survivors (all unchanged code)

These are explicitly retained test gaps or an equivalent mutation outside F9/F1;
the source statements are unchanged in this patch.

| File and line | Mutation | Reason retained |
| --- | --- | --- |
| `builder.py:158` | `HEADLINE_MIN_WORDS - 1` becomes `+ 1` | Legacy tests do not exercise a cut boundary at the minimum retained word count. |
| `builder.py:158` | subtraction literal `1` becomes `0` | Same minimum-boundary test gap; the cut loop loses its shortest permitted boundary. |
| `builder.py:167` | date-plus-slot offset `+` becomes `-` | Existing tests check valid, deterministic phrase variation, not the exact variant index. |
| `builder.py:181` | delete unary minus on outlet count | Existing tests do not pin the secondary event order for a confidence tie. |
| `builder.py:194` | product count `>` becomes `>=` | Existing tests do not isolate positive model count with zero product count. |
| `builder.py:210` | no-headline cut flag `False` becomes `True` | Legacy builder tests assert the missing headline without asserting its cut flag. Writer tests do assert the flag on removal. |
| `builder.py:296` | Key-results reaction count increment `1` becomes `0` | Existing tests verify that reaction text, but not the only-Key-results `reactions_used` counter. |
| `writer.py:150` | `zip(..., strict=True)` becomes `False` | Equivalent under the function's invariant: `found` is constructed from exactly the same `links`, so the two lengths cannot differ. |

### Coverage-filtered mutation sites

Six unchanged sites were not executed by mutator: `builder.py:128` (the `_Event.score`
property's multiplication), `writer.py:199` (a multiline signature default),
`writer.py:259` (a multiline call's `copy=True`), `bulletin_input.py:62` (one date
comparison), and two operators at `bulletin_input.py:63` (window comparison and
subtraction). No new-code mutation site was uncovered. The multiline signature,
call and SQL-expression sites are consistent with the existing
`mutator-lcov-multiline-sites-uncovered` troubleshooting case; the called functions
and median-window behavior are exercised by feature tests. These unchanged sites
were not force-mutated in this task.

## Limitations

No live model evaluation was performed; all writer calls in these tests use fakes.
F1's semantic behavior therefore still needs the separately arranged model review.
The separate reviewer was not spawned by this session, as the task requires.

PostgreSQL integration tests were skipped because `AINEWS_TEST_POSTGRES_URL` was
unset. Full pytest, broad lint, doc check, crapper and dryer were each run in the
requested order before mutation testing. They were not repeated after the final
one-line regex correction and its three regression cases, per the speed rule;
the failed feature test and affected mutation sites were rerun instead. The
correction does not change the helper's control flow or complexity; its final
behavior is covered by the scoped tests and all ten killed helper mutations.
The CRAP and duplication snapshots therefore precede that final expression edit.
