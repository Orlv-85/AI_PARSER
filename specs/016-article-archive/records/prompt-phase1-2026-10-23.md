# Prompt: spec 016 phase 1 - archive storage and prune safety (2026-10-23)

You implement **phase 1 of spec 016** (tasks T001-T004) in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
The coordinator is session `ai-parser-d4`; report to it by SendMessage when done. The owner writes
Russian and takes part minimally; do not ask the owner design questions (AGENTS.md "Owner And
Questions": decide, then report).

## Why now

Every deploy (`scripts/deploy_prod.sh`, prune step) and nightly db-maintenance run
`ai-news prune --older-than-days 800` and delete the oldest articles with their text. Phase 1 makes
prune copy those rows into archive tables first, in the same transaction.

## Read first (nothing else up front)

1. `AGENTS.md` (rules: feature docs next to code, validation, owner questions).
2. `specs/016-article-archive/spec.md`, `plan.md`, `tasks.md` - phase 1 only is in scope.
3. `src/app/storage/article_repo.py` (`count_older_than`, `prune_older_than`),
   `src/app/storage/models_sql.py`, the newest migration
   `src/app/storage/migrations/versions/c3a8e5d27f14_add_daily_signal_briefs.py`, existing prune
   tests (`grep -rl prune tests`).

## Steps

1. Worktree: `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch` then
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add ../AI_PARSER-wt-016-p1 -b feat/016-archive-storage-20261023 origin/master`.
   Work only there. Do not touch the main folder. Run checks with
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/<tool>` from the worktree root (venv1 is editable on the
   main folder).
2. T001 code doc first: `src/app/core/archive/capture.md` (header `<!-- code-doc` / `module:` /
   `covers:` / `-->`; sections Behavior with a Mermaid diagram and `Tests:` per rule, Decisions,
   Invariants, Code map, Tests). Only rules, names, tests and globs this PR ships
   (`scripts/check_code_docs.py` fails on names that do not exist). Register the doc in
   `docs/README.md`, `README.md`, `src/app/README.md`. Create `src/app/core/archive/__init__.py`
   and `capture.py` (docstring names the doc; constants from plan.md; `archive_articles(session,
   articles)`, sync, no network).
3. T002: `ArchiveDocument`, `ArchiveText` in `models_sql.py`; migration
   `<rev>_add_article_archive.py` with `down_revision = "c3a8e5d27f14"`, working on SQLite and
   PostgreSQL; `src/app/storage/archive.py` `ArchiveRepo` (upsert document, add version by hash,
   purge selection, status counts, size).
4. T003: `ArticleRepo.prune_older_than` archives the rows it deletes first, same transaction.
   `count_older_than` and `prune --dry-run` behave exactly as now (no archive writes).
   CLI flags and output of `ai-news prune` unchanged.
5. T004 tests (names exactly as in tasks.md T004), in `tests/unit/test_article_archive.py` unless
   tasks.md says otherwise; migration round trip next to the existing migration tests.
6. Checks, in this order:
   - `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests/unit/test_article_archive.py tests/unit/test_daily_signals_migration.py` plus the prune test files;
   - alembic `upgrade head` then `downgrade -1` then `upgrade head` on a copy of a local SQLite DB
     (never the main folder's DB file itself);
   - full gate: `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`,
     `PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
7. Commit (ASCII, conventional): `feat(archive): archive tables and archive-before-prune (016 phase 1)`,
   ending with the Co-Authored-By line your harness gives. Push the branch and open the PR:
   `gh pr create --base master --title "feat(archive): archive tables, prune archives before delete (016 phase 1)" --body "<summary, tests run with results, migration up/down result, open questions>"`.
   Do not merge, do not tag, no prod access.

## Out of scope

Phase 2+ (CLI `archive capture/status/purge`, downloads, nightly job), restoring the 79 already
pruned articles, any change to deploy scripts, retention value, fetch/digest units.

## Report to the coordinator (SendMessage to `ai-parser-d4`)

PR link and head SHA; files changed; the tests added (names); full gate output summary (passed /
failed counts, lint result, check_code_docs result); migration up/down result; every decision you
made that the spec did not fix, one line each, and any doubt about the spec.
