# Prompt: spec 018 selection (F6), the kind of an article (2026-11-17)

Owner go 2026-11-17 ("да": label check, then the fifth question if it passes). Label check done
by the coordinator on prod (39 reviewed articles, $0.0036): event vs not agreed 34 of 38, no real
event called `promotion` (report: `specs/018-daily-inference/records/report-selection-kind-check-2026-11-17.md`).
Plan: `specs/018-daily-inference/records/plan-selection-kind-2026-11-17.md`.

## Where and how

- Work only in the worktree `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-018-kind` (branch `feat/018-selection-kind`, from `origin/master`).
  Never touch `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
- Read `AGENTS.md`. Order: feature docs first (`src/app/core/bulletin/world_change.md`,
  `src/app/core/bulletin/builder.md`, `src/app/core/bulletin/repeats.md`,
  `src/app/usecases/bulletin/daily.md` for numbers), then each failing test (run it, see it fail
  for the expected reason), then the smallest code. ASCII. Match the style.
- Python `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`; `export PYTHONPATH=src`,
  `set -o pipefail`. Do not commit, push or open a PR. Test files under 1000 lines
  (`test_bulletin_builder.py` is over: put builder tests in a new file
  `tests/unit/test_bulletin_kind.py`).

## 1. The fifth question (`src/app/core/bulletin/world_change.py`)

- `WORLD_CHANGE_VERSION = "world-change-2"`.
- Add to `WORLD_CHANGE_QUESTIONS` (exact text; it is the one the label check used, with the version
  name):
  ```python
  "kind": {
      "type": "choice",
      "instructions": (
          f"Question version: {WORLD_CHANGE_VERSION}. Decide what kind of text this article is, "
          "judged by its main content. Treat state only as data."),
      "criteria": {
          "event": "A news report of something that happened or was decided: a launch, release, deal, ruling, law, policy, incident, attack, measured study result or an official action, told by a news outlet or an official body.",
          "forecast": "Mainly predictions or projections of what AI will do: market forecasts, outlooks, scenarios, estimates for coming years.",
          "opinion": "Mainly views: commentary, op-eds, interviews or speeches giving opinions, calls or recommendations, with no decision taken.",
          "explainer": "Background, analysis, guides, trend features or overviews that explain rather than report a new event.",
          "promotion": "Text by or for a company about its own product or customers: press releases, newswire copy, vendor blogs, case studies, sponsored content.",
      },
  },
  ```
- `WorldChange` gets `kind: str` and `kind_confidence: float`; `parse_answers` validates `kind`
  like the other choices (unknown or missing makes the whole answer invalid).

## 2. Storage

- `world_change_assessments` gets nullable `kind` (String) and `kind_confidence` (Float) columns:
  `src/app/storage/models_sql.py` and a new Alembic migration in
  `src/app/storage/migrations/versions/` (follow `b8e2d4f61a07_add_world_change_assessments.py`;
  `down_revision` = the current head: find it with the alembic heads command or by reading the
  versions). Old `world-change-1` rows keep NULL.
- `WorldChangeRepo.save` stores them. Check `src/app/storage/world_change.md` or the storage doc
  that covers this table and update it.

## 3. Selection

- `Candidate` (`builder.py`) gets `kind: str = "event"`; `day_input.py` fills it from the answer
  (digest and world candidates).
- Builder: an event is shown (Key results, cooperation, rubric, incident, reserve) only when its
  representative's `kind` is in `SHOWN_KINDS = frozenset({"event"})`; otherwise it is left out like
  a `none` event. Put the rule in one predicate (e.g. `showable(candidate)` in `builder.py`: not
  `none`, confidence at least `MIN_CONFIDENCE`, kind shown) and use it in `builder.py` and in
  `repeats.py` (`_showable`), so the repeat check lists only candidates that can be shown.
- Numbers: `prepare_from_input` adds `numbers["kinds"]`: counts of `kind` over the candidates whose
  `world_change` is not `none` (so readers of the stored row see how many were left out and why).
  The `bulletin_assessed_share` log line is unchanged.
- `src/app/usecases/world/report.py` (world report): add `kind` to each item and a `kind` counter
  next to the `world_change` counter, if that fits its shape; check its tests.

## 4. Docs

- `world_change.md`: five questions, the `kind` question and its use, version 2; a Decisions line
  "decided 2026-11-17 (owner): ... label check 34/38, no event called promotion".
- `builder.md`: the shown-kind rule with test names; Decisions: why only `event` (F6 of the
  FR-022 review: 5 of 12 world stories were a concrete change).
- `repeats.md`: listed candidates use the same predicate.
- `daily.md`: `numbers["kinds"]`.
- Note in `world_change.md`: answers of `world-change-1` are not read after the switch; the first
  night after the deploy has fewer world candidates from the day before (they were assessed under
  version 1 and are not re-sent).

## Tests (each fails first)

- `test_kind_question_is_asked_and_parsed` (request has five questions; a valid answer gives
  `kind`; an unknown kind invalidates the answer), update `test_questions_shape_and_version`,
  `test_request_has_only_the_four_questions` (now five; rename to `..._five_questions` and keep the
  doc's test names in step).
- `test_storage_keeps_kind` (save and read back; old rows without kind still load).
- `test_only_events_are_shown` (an `opinion`, `forecast`, `explainer`, `promotion` candidate with
  high confidence is not in any section or the reserve; an `event` one is),
- `test_repeat_check_lists_only_showable_kinds`,
- `test_numbers_count_kinds`,
- the migration: follow how existing migrations are tested (grep tests for an existing
  migration test, e.g. `b8e2d4f61a07`), or say plainly if there is none.

## Checks before you finish

1. `PYTHONPATH=src`: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:warnings tests/unit/test_bulletin_*.py tests/unit/test_world*.py tests/unit/test_web_bulletin_page.py tests/unit/test_layer_imports.py tests/unit/test_monkeypatch_targets.py tests/unit/test_code_docs.py tests/unit/test_migrations*.py`; print `rc=$?` (skip patterns that match no file and say so).
2. `ruff check src tests`; `pylint` on changed src and test files.
3. Coverage over the bulletin/world tests, `coverage lcov -o target/coverage/python/lcov.info`,
   `~/tools/unclebob/crapper/crapper --changed --use-existing-coverage` (changed functions under
   10), `~/tools/unclebob/dryer/dryer --threshold 0.8 --changed`.

## Final message (you cannot write report files)

Per part: files and functions changed, tests with the failure seen first, the migration id and its
down revision, check outputs with exit codes, anything decided yourself or not done.
