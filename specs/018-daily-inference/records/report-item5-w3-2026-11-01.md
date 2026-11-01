# Report: spec 018 item 5, world stream W3 storage (2026-11-01)

Implementer: background agent (Sonnet), prompt `prompt-item5-w3-2026-11-01.md`. Saved by the
coordinator from the agent's final message.

PR: https://github.com/Orlv-85/AI_PARSER/pull/164 (branch `feat/018-world-w3-storage`, base master).

## Files

- `src/app/core/world/world.md`: Storage section, 3 decisions, 1 invariant, code map, tests; `covers`
  includes `src/app/storage/world.py`.
- `src/app/storage/models_sql.py`: `WorldCandidate`, `WorldFile`.
- `src/app/storage/migrations/versions/c9f3a7e15b28_add_world_candidates_and_files.py`: new head,
  down_revision `b8e2d4f61a07`.
- `src/app/storage/world.py`: `WorldRepo`.
- `tests/unit/test_world_storage.py`: 11 tests.
- `tests/unit/test_period_signals_migration.py`: head check expects `c9f3a7e15b28`.

## Checks (agent)

- `make lint`: ruff, mypy, pylint 10.00/10.
- Full pytest `-o addopts=""`: 1504 passed, 1 skipped.
- `scripts/check_code_docs.py`: ok (10 docs).
- `alembic upgrade head` / `downgrade -1` on temp SQLite: ok. PostgreSQL not run.

## Decided by the agent

- `world_files.state` is `done` or `missing`; primary key `(stamp, kind)`; `stamp` 14-digit string;
  `done_files(day)` returns only `done`, so `missing` files are retried.
- `published_at` parsed from the GDELT stamp (null if unparsable); `country_hint` from `tld_hint`;
  `match_kind` from `match`.
- `priority`, `screen_confidence` nullable floats.
- A repeat hash changes nothing (title, fields, state, `first_seen_at`); repeats in one batch counted.
- `cluster_key`: title casefolded, non-word runs to one space, first 60 chars; stored only.
- Final states `screened_out`, `no_text`, `assessed`; `failed` may return to `new`, `screened_in`,
  `text_ready`; a move to `failed` increments `attempts` and stores the error; other moves clear it.
- `prune` also deletes `world_files` rows older than `WORLD_RETENTION_DAYS` (30), beyond the prompt,
  to stop ~192 rows/day growth; written in the doc as decided by the agent.
- FR-016 import scan allows only world code, `models_sql.py` and `cli/main.py` to import world storage.
- Commit trailer `Co-Authored-By: Claude Sonnet 5.5` (the model that wrote it).

## For W4

- `WorldRepo(session)`; `upsert_candidates(iter of gdelt.Candidate, now=None)` returns
  `(new, repeats)`, flushes, caller commits.
- `record_file(stamp, kind, "done"|"missing", rows=, matched=, error=)` per file; `done_files(date)`
  before scanning a day; `prune()` returns `(candidates, files)`.
- File stamp = first 14 chars of the file name. `storage/world.py` imports
  `app.core.world.gdelt.Candidate`, so core world code must never import storage.

## For W5

- `candidates_in_state(state, limit=)` oldest first. Step A: `new` -> `transition(row,
  "screened_in"|"screened_out", screen_confidence=, priority=)`. Step B: `screened_in`/`text_ready`
  -> `assessed`, `no_text` (from `screened_in`) or `failed` (`error=`); else `InvalidTransition`.
- `world_change_assessments` keys unchanged: `(url_canonical_hash, question_version)`, `article_id`
  nullable; W5 joins on `WorldCandidate.url_canonical_hash` with `article_id=None`.
- No outlet-count column: W5 counts rows per `cluster_key` (indexed) and writes `priority`.

## Questions for the owner

None.
