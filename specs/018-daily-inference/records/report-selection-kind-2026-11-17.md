# Report: the `kind` question and event-only selection (2026-11-17)

Implementer: background Claude agent (Sonnet), prompt `prompt-selection-kind-2026-11-17.md`; saved
by the coordinator from the agent's final message, shortened.

## Done
- `world_change.py`: `WORLD_CHANGE_VERSION` `world-change-2`, `kind` question (label-check text),
  `WorldChange.kind`/`kind_confidence` (defaults `"event"`/`0.0` at the end so older positional
  constructions in tests stay valid; `parse_answers` always fills them), strict validation.
- Storage: nullable `kind` (`String(16)`), `kind_confidence` (`Float`) on
  `world_change_assessments`; migration `d7f3a9b25c61` (down `a6b0180c0001`, adds a column only if
  missing, `batch_alter_table`); `WorldChangeRepo.save` stores them. Deploy runs
  `alembic upgrade head` (`scripts/deploy_prod.sh`).
- Selection: `Candidate.kind`, `SHOWN_KINDS = {"event"}`, `showable()` in `builder.py` used by
  `_events` and by `repeats.py`; `day_input.py` fills kind; `numbers["kinds"]` in
  `prepare_from_input`; world report gets `kind` per sample and a `kind` counter.
- Docs: `world_change.md`, `builder.md`, `repeats.md`, `daily.md`, `src/app/core/world/world.md`.

## Tests (failed first)
`test_questions_shape_and_version`, `test_kind_question_is_asked_and_parsed`,
`test_request_has_only_the_five_questions`, `test_kind_migration_adds_nullable_columns`,
`test_storage_keeps_kind`, `test_only_events_are_shown`, `test_kind_of_the_representative_decides`,
`test_showable_needs_an_event`, `test_numbers_count_kinds`, `test_loader_fills_kind_from_the_answer`,
`test_repeat_check_lists_only_showable_kinds`; fixtures and exact-number tests updated (world
screen journal file names carry `world-change-2`; migration head test).

## Checks
Bulletin, world, web, layer, monkeypatch, code-docs, period-signals-migration, page-views tests
rc=0; ruff clean; pylint 10.00 (one `too-many-instance-attributes` disable on `WorldChange`);
crapper with coverage: changed functions under 10 (`_repeat_pairs` 10.0, untouched); dryer none.

## Review (fresh Claude agent, Sonnet, `prompt-selection-kind-review-2026-11-17.md`)
Ready after small fixes; no production defect (migration linear, plain ADD COLUMN on PostgreSQL;
world journal name does not carry the question version; `showable` is the only gate). Fixed by the
coordinator:
- F1: an event told by a news report and an opinion piece was dropped when the opinion had the
  higher confidence. Now the best-confidence showable member leads (`_events`); test
  `test_event_member_represents_a_mixed_event` (failed first: IndexError, nothing shown);
  decided by the coordinator as part of the approved "show events" rule.
- F2: "four questions" in `screen.py` docstring and `world.md` diagram -> five.
- F3/F4: `world_change.md` says a rerun of a past day asks its digest articles again once (about
  $0.015) and that the world report counts v1-assessed items that first night.
- F5: Decisions line: `kind_confidence` stored, not used.
After: scoped tests rc=0, ruff clean, pylint 10.00.
