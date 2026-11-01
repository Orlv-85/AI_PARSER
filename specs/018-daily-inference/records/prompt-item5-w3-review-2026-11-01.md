# Prompt: review of PR #164, world stream W3 storage (2026-11-01)

You review PR #164 (`feat/018-world-w3-storage`). You did not write it. **Read-only: no commits,
pushes, merges, PR comments, paid calls or production access.** Report in English.

## Read

- `gh pr view 164`, `gh pr diff 164`, `gh pr checks 164`.
- PR worktree: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-a2a8354462d61fb67`
  (do not edit it). There: `AGENTS.md`; the plan
  `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md` (6.1 Storage,
  Retention, Failure handling; 6.2 step 3); the prompt `records/prompt-item5-w3-2026-11-01.md`;
  spec FR-014..FR-018.
- The implementer's report: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/018-daily-inference/records/report-item5-w3-2026-11-01.md`
  (decisions it made; judge each).

## Check

1. Migration: head chain from `b8e2d4f61a07`; types and indexes valid on SQLite **and PostgreSQL**
   (unique hash, composite key, string lengths, timezone columns like the other tables); downgrade
   drops cleanly; the head test update.
2. Canonical hash: the same canonicalize and hashing as `articles` (find it and compare).
3. `WorldRepo`: upsert by hash is idempotent (rerun, repeats inside a batch, concurrent rerun after a
   crash); `done_files`/`record_file` let W4 skip processed stamps and retry `missing`; transition
   table matches plan states and does not allow illegal moves; `attempts`/error handling; prune by
   age with correct cutoff (timezone), touches no archive tables.
4. FR-016: nothing in web/digest/ingestion reads the world tables; the import-scan test really
   fails when it should (not vacuous).
5. Doc `world.md` matches the code; each rule names tests or says none; registrations unchanged where
   needed; `scripts/check_code_docs.py`.
6. Tests test behavior, not mocks; missing cases.
7. Run in that worktree:
   `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_world_storage.py tests/unit/test_period_signals_migration.py | tail -3`,
   ruff on `src tests`, and alembic `upgrade head` / `downgrade -1` on a temp SQLite file.
8. Quality tools (advisory, not gates), on the PR's source files only:
   `~/tools/unclebob/dryer/dryer src/app/storage/world.py src/app/storage/models_sql.py` and
   `~/tools/unclebob/crapper/crapper --no-coverage src/app/storage/world.py`. Report new duplicates
   with score >= 0.8 and functions with complexity >= 10. They write `.metrics/` into the worktree;
   delete that directory afterwards.

## Report (final message)

Verdict (merge / merge after fixes / do not merge); findings by severity with file:line, the concrete
failure and a one-line fix; "must fix" separate from "nice to have"; checks you ran with results.
