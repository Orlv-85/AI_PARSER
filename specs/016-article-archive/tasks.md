---
description: "Tasks: full-text article archive (A1, A3)"
---

# Tasks: Full-text article archive (A1, A3)

**Input**: `specs/016-article-archive/spec.md`, `plan.md`
**Prerequisites**: none; A0 (off-site backups) is done.

One task = one PR, in this order. Each PR: work in a worktree off `origin/master`; the code doc
`src/app/core/archive/capture.md` is edited first and matches the code at the end of the PR;
scoped checks while working, then the full gate before push (`make lint PYTHON=./venv1/bin/python`,
`./venv1/bin/pytest`, `./venv1/bin/python scripts/check_code_docs.py`). Do not merge; deploys are
the owner's (release/tag workflows).

## Format: `[ID] [Story] Description`

## Phase 1: Storage and retention safety (US1) - one PR

- [ ] T001 [US1] Code doc first: create `src/app/core/archive/capture.md` (header, Behavior for
  storage, sync and prune rules, Decisions, Invariants, Code map, Tests) and register it in
  `docs/README.md`, `README.md`, `src/app/README.md`. Create `src/app/core/archive/__init__.py`
  and `capture.py` with the docstring naming the doc, the constants of plan.md and
  `archive_articles(session, articles)` (sync, no network). `scripts/check_code_docs.py` fails on
  names that do not exist yet: each PR adds to the doc only the rules, code names, test names and
  `covers` globs it ships (the script glob comes with T010).
- [ ] T002 [US1] `ArchiveDocument`, `ArchiveText` in `src/app/storage/models_sql.py`; migration
  `<rev>_add_article_archive.py` (`down_revision = "c3a8e5d27f14"`); `src/app/storage/archive.py`
  `ArchiveRepo` (upsert document, add version by hash, purge selection, status counts, size).
- [ ] T003 [US1] `ArticleRepo.prune_older_than` archives the rows it deletes first, same
  transaction; `count_older_than` and `prune --dry-run` unchanged.
- [ ] T004 [US1] Tests: `test_sync_creates_document_and_content_version`,
  `test_sync_versions_only_on_text_change`, `test_recollected_article_reuses_document`,
  `test_prune_archives_rows_before_delete`, `test_prune_dry_run_does_not_archive`,
  `test_prune_and_evidence_purge_keep_archive_rows`, `test_archive_not_imported_by_web_or_mcp`,
  `test_article_archive_migration_round_trip`.

**Checks**: `./venv1/bin/pytest tests/unit/test_article_archive.py tests/unit/test_daily_signals_migration.py`
plus existing prune tests (`grep -rl prune tests`); `alembic upgrade head` and `downgrade -1` on a
local SQLite copy; full gate.
**Why first**: every deploy runs `prune --older-than-days 800`; 79 stored articles (71 with text)
are past that cutoff today.

## Phase 2: Seed and operator commands (US1, US3) - one PR

- [ ] T005 [US1] `ai-news archive capture` with `--all`, `--no-download`, `--max-seconds` (steps 1,
  2 and 8 of plan.md only; download steps come in T008); `ai-news archive status`.
- [ ] T006 [US3] `ai-news archive purge (--url | --source | --host) [--apply]`.
- [ ] T007 Tests: `test_capture_window_and_seed_make_no_requests`,
  `test_archive_purge_dry_run_and_apply`, `test_capture_summary_reports_coverage` (sync fields);
  `docs/deploy.md`: seed, status, purge commands (operator section, no Behavior repeated).

**Checks**: scoped tests; `ai-news archive --help`, `ai-news archive capture --all --no-download`
and `ai-news archive status` on a local SQLite DB with a few articles; full gate.
**After deploy (owner yes needed, prod write)**: `docker compose -f docker-compose.prod.yml run --rm
app ai-news archive capture --all --no-download`, then `archive status`; expect 7079+ documents and
3030+ versions (SC-001).

## Phase 3: Downloads with retries (US2) - one PR

- [ ] T008 [US2] Steps 3-7 of plan.md in `capture.py`: due selection, reuse of the daily-publish
  cache (read-only), downloads through `SourcePageDownloader` on `data/archive/source-cache`, caps
  per run and per host, stop at `--max-seconds`, retry table, retry clears only the archive cache
  entry, outage not counted, deletion of raw page dirs older than `ARCHIVE_RAW_KEEP_DAYS`.
- [ ] T009 [US2] Tests: `test_capture_reuses_daily_publish_page`,
  `test_capture_downloads_and_archives_page`, `test_capture_gives_up_on_permanent_issues`,
  `test_capture_retry_schedule_then_gives_up`, `test_capture_retry_clears_only_archive_cache`,
  `test_capture_respects_caps_and_time`, `test_capture_outage_keeps_attempts`,
  `test_capture_deletes_old_raw_pages`; extend `test_capture_summary_reports_coverage`.
  All with `httpx.MockTransport`, no network.

**Checks**: scoped tests; `tests/unit/test_article_evidence_cache.py` and
`tests/unit/test_daily_enrichment.py` unchanged and green (shared downloader); full gate.

## Phase 4: Nightly job (US2) - one PR

- [ ] T010 [US2] `scripts/run_daily_archive_job.sh` (release image as in the other jobs,
  `flock -w 1800` on `/tmp/ai-news-auto-update.lock`, `timeout -k 30 1680`, named container removed
  on timeout, `--max-seconds 1500`, always exit 0 with one stderr line on failure);
  `scripts/install_daily_timers.sh` adds `archive` at 03:00 UTC with `TimeoutStartSec=3600` and its
  log `logs/daily-archive.log`.
- [ ] T011 Tests: `test_archive_job_script_is_isolated` (in `tests/unit/test_deepseek_digest.py`,
  next to the fetch/digest job tests), `test_install_timers_includes_archive` (in
  `tests/unit/test_daily_timers.py`); code doc Behavior gets the schedule rule.

**Checks**: `bash -n scripts/*.sh`; scoped tests; full gate. Production-sensitive: no change to
fetch/digest units, lock path, ports or retention.
**After deploy**: first night, read `logs/daily-archive.log` (`archive_capture_finished`), then
`archive status` after 7 nights for SC-002 (coverage >= 90%).

## Phase 5 (optional, P3): admin stats

- [ ] T012 Archive counts (documents, archived, coverage of the window, size) on the admin stats
  page, numbers only, never text; behind auth; test that the public pages and APIs do not show them.
  Skip unless the owner asks.

## Dependencies

T001-T004 -> T005-T007 -> T008-T009 -> T010-T011 -> (T012). The seed run needs Phase 2 deployed.
A2 (backfill downloads) is a new spec after Phase 4 has run for a week.
