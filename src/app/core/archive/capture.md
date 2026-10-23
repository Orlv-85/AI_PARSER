<!-- code-doc
module: src/app/core/archive/capture.py
covers:
  - src/app/core/archive/*.py
  - src/app/storage/archive.py
  - src/app/storage/migrations/versions/*article_archive*.py
-->
# Article archive

Private, permanent copy of collected articles: one document per canonical URL hash and
append-only text versions. Retention and cleanup never delete it. Spec:
`specs/016-article-archive/spec.md` (phases 1-2: storage, archive-before-prune, seed and
operator commands; downloads come in phase 3).

## Behavior

```mermaid
flowchart LR
  prune["ai-news prune"] --> select["Select rows past the cutoff"]
  select --> sync["archive_articles: upsert document per canonical hash"]
  sync --> long{"content >= ARCHIVE_MIN_TEXT_CHARS?"}
  long -- yes --> hash{"new text sha256 for the document?"}
  hash -- yes --> version["Add article_content version; document archived"]
  hash -- no --> keep["No new version"]
  long -- no --> pending["Document only, state pending"]
  version --> delete["Delete aliases and articles, same transaction"]
  keep --> delete
  pending --> delete
  cli["ai-news archive capture"] --> window["Window: first seen within ARCHIVE_LOOKBACK_DAYS, or --all"]
  window --> batches["archive_articles per CAPTURE_BATCH_SIZE rows; commit per batch"]
  batches --> summary["archive_capture_finished JSON line"]
```

- `archive_articles` makes one `ArchiveDocument` per `url_canonical_hash` with the article's
  metadata and adds an `ArchiveText` (`origin = article_content`, `ARTICLE_CONTENT_VERSION`) only
  when the content has at least `ARCHIVE_MIN_TEXT_CHARS`. A document with a version is `archived`,
  without one `pending`. No network. Tests: `test_sync_creates_document_and_content_version`.
- A version is added only when its SHA-256 differs from every stored version of the document; older
  versions stay. Tests: `test_sync_versions_only_on_text_change`.
- A hash that was pruned and collected again reuses its document: metadata and `article_id` are
  updated, `first_seen_at` is kept. Tests: `test_recollected_article_reuses_document`.
- `ArticleRepo.prune_older_than` archives every row it is about to delete, in the same transaction,
  before the delete; a rollback undoes both. `count_older_than` and `prune --dry-run` write
  nothing. Tests: `test_prune_archives_rows_before_delete`, `test_prune_archive_rolls_back_with_delete`,
  `test_prune_dry_run_does_not_archive`.
- `ai-news archive capture` syncs articles discovered within `ARCHIVE_LOOKBACK_DAYS` (all
  articles with `--all`) through `archive_articles`, in batches of `CAPTURE_BATCH_SIZE` with a
  commit per batch. It makes no network request; with or without `--no-download` there is no
  download step yet, and `--max-seconds` only bounds the future download step. Tests:
  `test_capture_window_and_seed_make_no_requests`.
- The capture ends with one `archive_capture_finished` JSON log line, which the CLI also prints:
  `window_days` (null with `--all`), `articles_synced`, `window_documents` and `window_archived` (documents first seen
  in the window), `coverage_pct`, `new_versions` by origin, `archive_bytes`,
  `archive_size_warning` (from `ARCHIVE_SIZE_WARN_BYTES`). Tests:
  `test_capture_summary_reports_coverage`.
- `ai-news archive status` is read-only and prints counts by state, versions, size, coverage per
  first-seen day of the last `ARCHIVE_LOOKBACK_DAYS` and the top hosts without text. Tests:
  `test_capture_summary_reports_coverage`.
- Prune and `purge_evidence` never delete archive rows; only `ArchiveRepo.purge` with `apply=True`
  does. `ai-news archive purge` takes exactly one of `--url`, `--source`, `--host` (else exit 2),
  prints document and version counts, and deletes only with `--apply`. Tests:
  `test_prune_and_evidence_purge_keep_archive_rows`, `test_archive_repo_purge_status_and_size`,
  `test_archive_purge_dry_run_and_apply`.
- No module under `src/app/web` (pages, API, MCP) imports `app.core.archive` or
  `app.storage.archive`. Tests: `test_archive_not_imported_by_web_or_mcp`.
- The migration creates both tables only when missing and its downgrade drops them. Tests:
  `test_article_archive_migration_round_trip`.

## Decisions

- Same database, two tables, no foreign key to `articles` or `sources`: backups already cover the
  database, and documents must outlive their articles (plan.md, "Where the archive lives").
- Stored content is copied under `ARTICLE_CONTENT_VERSION`, because ingestion does not record which
  extractor produced `articles.content` (plan.md, data model).
- decided 2026-10-23 (agent): `ArchiveRepo.size_bytes` uses `pg_total_relation_size` on PostgreSQL
  and the summed text length elsewhere; SQLite has no per-table size without the optional `dbstat`.
- decided 2026-10-23 (agent): `document_id` has a plain foreign key without cascade; `purge` deletes
  versions explicitly, so SQLite (foreign keys off) and PostgreSQL behave the same.
- decided 2026-10-23 (agent): the capture window counts documents by `first_seen_at`, so the
  coverage of a window does not depend on rows that prune has already removed.

## Invariants

- Archive rows are deleted only by `ArchiveRepo.purge` with `apply=True`.
- `archive_texts` is append-only; `(document_id, text_sha256)` is unique.
- One document per `url_canonical_hash`.
- Raw HTML is never stored in the archive tables.

## Code map

- `capture.py`: constants, `archive_articles` (sync of stored articles, no network), `capture`
  (window, batches, summary) and `status`.
- `cli/main.py`: `archive` Typer group (`capture`, `status`, `purge`).
- `storage/archive.py`: `ArchiveRepo` (upsert document, add version by hash, purge selection,
  state counts, window coverage, hosts without text, size).
- `storage/models_sql.py`: `ArchiveDocument`, `ArchiveText` (tables `archive_documents`,
  `archive_texts`).
- `storage/migrations/versions/e7b4c2a9d150_add_article_archive.py`: additive migration after
  `c3a8e5d27f14`.
- `storage/article_repo.py`: `prune_older_than` calls `archive_articles` before its deletes.

## Tests

- `tests/unit/test_article_archive.py`: sync, versions, re-collection, prune, evidence purge, repo
  purge/status/size, capture and status, `archive purge` CLI, web import guard.
- `tests/unit/test_daily_signals_migration.py`: migration round trip.
