# Prompt: spec 016 - archive the 79 articles pruned on 2026-10-23 from a dump (2026-10-23)

You build a small, tested tool that archives articles from **another database** (a restored dump)
into the archive of the current database, in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
Phases 1-2 of spec 016 are merged and deployed (v0.1.122). The coordinator is session `ai-parser-d4`;
report to it by SendMessage when done. Do not ask the owner design questions (AGENTS.md).

## Background

The v0.1.118 deploy (2026-10-23, before phase 1) pruned 79 articles (71 with text, published 2017)
past the 800-day cutoff. They exist in the dump `backups/postgres_20261022T074337Z.sql.gz` on the
server (also on Backblaze B2). Goal: they end up as archive documents (with text versions where long
enough) in prod, without touching `articles`.

## Design (fixed; report if something does not hold)

- New command `ai-news archive import-db --source-url <SQLAlchemy URL> [--apply]`:
  reads `articles` (+ `sources` for `source_key`) from the source database with its own engine,
  read-only; selects rows whose `url_canonical_hash` is **neither** in the current `articles`
  **nor** in `archive_documents` (so existing documents never get an older text version); passes
  them to `archive_articles` on a session of the current database in batches
  (`CAPTURE_BATCH_SIZE`), committing per batch. Dry run by default: prints JSON with
  `source_articles`, `selected`, `selected_with_text` and does not write. With `--apply` prints
  the same plus `documents`, `new_versions`.
- Source rows are mapped to transient `Article` objects (not added to the current session) or
  `archive_articles` gets an equivalent input - your choice, keep `archive_articles` the single
  path that writes archive rows.
- Never write to the source database. No network.
- Code doc `src/app/core/archive/capture.md` first (Behavior rule with `Tests:`), operator command
  in `docs/deploy.md` "Article archive" section, including how to load a dump into a scratch DB
  inside the `ai-news-db` container and drop it afterwards (see "Prod run" below).

## Steps

1. Worktree: `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch` then
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add ../AI_PARSER-wt-016-import -b feat/016-archive-import-db-20261023 origin/master`.
   Remove the p2 worktree. Checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/<tool>`.
2. Doc, code (`capture.py` + CLI in `src/app/cli/main.py`), tests in
   `tests/unit/test_article_archive.py`: `test_import_db_archives_only_missing_hashes` (two temp
   SQLite files: a hash present in current articles and one already archived are skipped, a missing
   one is archived with its text and `source_key`), `test_import_db_dry_run_writes_nothing`
   (also asserts the source DB file is unchanged).
3. Local run: copy of the local SQLite DB as source, a second copy with some articles deleted as
   target; dry run then `--apply`; report the JSON.
4. Full gate: `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
5. Commit `feat(archive): import missing articles from another database (016)` with your harness's
   Co-Authored-By line; push; `gh pr create --base master --title "feat(archive): archive import-db for pruned articles (016)" --body "<summary, checks, local run JSON, decisions, prod run commands>"`.
   Do not merge, do not tag, no prod access.

## Prod run (for the PR body; the coordinator runs it after deploy with the owner's yes)

Write the exact commands: create scratch DB `ainews_restore_20261022` in `ai-news-db`, load
`backups/postgres_20261022T074337Z.sql.gz` into it (check whether the dump has `CREATE DATABASE`/
`\connect` lines and how to load it into a differently named DB), run
`docker compose -f docker-compose.prod.yml run --rm app ai-news archive import-db --source-url postgresql+psycopg://...ainews_restore_20261022` (dry run, then `--apply`; use the driver
name the app actually uses), then drop the scratch DB. Expected: selected 79, with text 71.

## Report to the coordinator (SendMessage to `ai-parser-d4`)

PR link and head SHA; files changed; tests added; gate summary; local run JSON; the prod run
commands; decisions not fixed here, one line each.
