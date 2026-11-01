# Review: PR #164, world stream W3 storage (2026-11-01)

Reviewer: background agent (Sonnet), prompt `prompt-item5-w3-review-2026-11-01.md`, read-only.
Saved by the coordinator from the agent's final message.

**Verdict: merge.** No must-fix items.

## Nice to have

1. Concurrent insert: `src/app/storage/world.py:78-96` is check-then-insert; two concurrent writers
   make `flush` raise `IntegrityError` and lose the batch. Rerun after a crash is fine. Fix: single
   writer stated (W4 host lock) or `ON CONFLICT DO NOTHING`.
2. FR-016 scan misses relative imports (`tests/unit/test_world_storage.py:204-229`): `from ..storage
   import world` in core passes. Absolute forms fail as they should (checked by mutation). Fix:
   resolve `node.level > 0`.
3. Rules in `world.md` without tests: PostgreSQL claim (only SQLite tested; types valid by
   inspection), URL cut to 2048, `HASH_CHUNK` batching over 500, `error` cut to 255, exact prune
   cutoff, empty batch.
4. Invariant "core/world never imports storage" is not tested.
5. `transition` (`world.py:114`) raises `KeyError`, not `InvalidTransition`, for an unknown stored
   state (corrupt data only).
6. `nullable=False` columns have no `server_default` (model and migration agree).

## Checks found ok

Single head `b8e2d4f61a07` -> `c9f3a7e15b28`; create-if-missing; indexes match model; composite key
on `world_files`; tz-aware datetimes; downgrade drops both. Hash = `app.core.canonicalize.canonical_url_hash`
as in `articles` ingestion, computed on the full URL. Upsert idempotent; transitions 7x7 tested;
`done_files` returns only `done`; prune cutoff in UTC, archive and assessments untouched. Doc
matches code except item 3. All implementer decisions judged OK.

## Checks run

14 tests passed (`test_world_storage.py`, `test_period_signals_migration.py`); ruff ok;
`check_code_docs.py` ok; alembic upgrade/downgrade on SQLite ok; FR-016 scan mutation test; dryer:
no duplicates; crapper: max complexity 7. Not run: PostgreSQL, full pytest, `make lint` (CI lint and
tests passed later, checked by the coordinator).
