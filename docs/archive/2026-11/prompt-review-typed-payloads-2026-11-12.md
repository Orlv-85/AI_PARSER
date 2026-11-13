# Review: typed payloads instead of dict[str, Any] (2026-11-12)

Read-only review. Do not edit files, commit, push or use the network. Do not spawn sub-agents.

Branch `refactor/typed-signal-models`, one commit on top of `origin/master`:
`git diff origin/master...HEAD`. Goal: item 9 of a code review - computations kept their data in
`dict[str, Any]` with string keys mypy does not check. The change:

- `src/app/core/daily/signals_payload.py`, `src/app/core/periodic/period_payload.py`: TypedDicts of
  the stored daily and period payloads.
- `signals_compute.py`, `period_compute.py`: build those types; working fields that lived in
  `_`-keys (`_key`, `_ids`, `_unit`, `_delta`, `_type_rank`, `_pubs`, `_best`, `_links`) moved to
  dataclasses / tuples beside the item.
- `signals_brief.py`, `period_brief.py`, `writer.py`: `Packet`, `WriterPacket`, `WriterSummary`;
  model answers are `object` instead of `Any`; `ArticleRefs` now takes links, `of()` takes a link
  list.
- Boundaries: `storage/period_signals.py` (cast of loaded JSON), `usecases/periodic/period_brief_run.py`.
- Feature docs: `usecases/daily/signals.md`, `core/periodic/signals_period.md`, `core/bulletin/writer.md`.

Claimed: stored JSON byte-identical to master (key order included) over 1050 outputs of the test
fixtures; mypy with `MYPYPATH=src` has no new errors against master.

Check:
1. Behavior: any output value or key order that differs from master (sorting keys, `spike`
   flag now derived from `trailing_mean is not None`, kept-spike copies, `reason` on rising items,
   period `_ranked` / `_best_first` sort, `_MergedStory` label choice, writer `_evidence` order,
   `parse_writer` handling of non-dict story entries).
2. Defensive reads of stored payloads (old methodology versions, missing keys, non-dict entries)
   that the old code tolerated and the new code no longer does.
3. TypedDict fields whose declared type is wrong for a value actually stored (e.g. None).
4. Doc lines that do not match the code.

Run only: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:cacheprovider tests/unit/test_daily_signals_compute.py tests/unit/test_daily_signals_brief.py tests/unit/test_period_compute.py tests/unit/test_period_month.py tests/unit/test_period_brief_flow.py tests/unit/test_bulletin_writer.py`

Report: findings ranked by severity, each with file:line, the failing input and the wrong result;
"no findings" if none. Keep it short.
