# Report: spec 018 item 5, W6 text download (2026-11-01)

Implementer report (background agent, model sonnet), saved by the coordinator. PR #190, branch
`feat/018-world-w6-text`, commit 804a58a. No paid calls.

## Files

- New: `src/app/core/world_text.py` (`run_texts`, `archive_text_source`), `tests/unit/test_world_text.py`.
- Changed: `src/app/core/archive/capture.py` (`download_documents`, `only=` on `_download_step`),
  `src/app/storage/archive.py` (`ArchiveRepo.due(..., ids=)`), `src/app/storage/world.py`,
  `src/app/cli/main.py` (`world texts`; `world screen` passes the seam), `world.md`, `capture.md`,
  tests `test_archive_capture.py`, `test_world_storage.py`, `test_world_screen.py`.

## Checks (implementer)

ruff clean; `make lint` (mypy 252 files, pylint 10.00); full pytest 1805 passed, 1 skipped;
`check_code_docs.py --diff origin/master --strict` exit 0. dryer: none; crapper >= 10 only in old
code (`_download_step` 24, `archive_articles` 10, `capture` 10); `run_texts` split to stay under 10.

## Smoke

Temp SQLite, 5 real pages: 3 `text_ready` (wikipedia, bbc, theguardian), 2 `no_text` (reuters
robots, apnews 403); 0 `articles` rows, 3 archive text versions.

## Archive use

Top representative -> `archive_documents` via `archive_articles` with a transient `Article`; download
step fetches only those documents; text in `archive_texts`, origin `source_page`, found by
`url_canonical_hash`; candidate stores no text; no `articles` row; candidate prune leaves archive rows.

## Decided by the implementer

- Separate `ai-news world texts` (no key, no money); a day runs `screen`, `texts`, `screen` (W7).
- `no_text` keeps reason `text: <issue>` in `last_error`, no attempt counted (`transition` changed so
  it no longer clears the error for this move); W5 requeue never touches `no_text`.
- Outage or not attempted leaves `screened_in`; any other failure (incl. page timeout) -> `no_text`
  at once; the archive keeps its own retry schedule.
- A cluster whose representative is `no_text` is ranked by remaining outlets next run.
- Clusters with text keep their top places: never more than `WORLD_TOP_N` clusters fetched.
- World documents are ordinary archive documents (nightly capture counts and retries them).
- `run_screen` defaults to `no_text`; only the CLI passes `archive_text_source`. Dry run:
  `would_download`.

## For W7

`world texts` and the nightly archive share `data/archive/source-cache`: run under the host lock. No
time limit on `world texts` (downloader timeouts, at most 100 pages).

## Fixes after review (commits 34524f3, a343dcd)

1. `_documents` creates a document only for a hash without one; existing documents are read only.
   Test `test_world_text_keeps_metadata_of_a_real_archive_document`.
2. `WORLD_SOURCE_KEY = "world"` (`storage/archive.py`), set after `archive_articles` creates the
   document; excluded from `window_states` and from `due()` with `ids=None`
   (`test_archive_coverage_skips_world_documents`, `test_archive_due_skips_world_documents`); a real
   article with the same URL takes over by upsert (`test_real_article_takes_over_a_world_document`).
   Archive size warning still counts world texts (documented in `capture.md`).
3. Existing `failed` or `gave_up` document -> candidate `no_text`; only `pending` documents are
   downloaded; tests `test_world_text_existing_failed_or_gave_up_document_is_no_text`,
   `test_world_text_next_run_tries_the_next_outlet`,
   `test_world_text_no_text_cluster_ranks_by_remaining_outlets`.
4. N bound per run in `world.md`. 5. New doc lines within 100 characters.

Mutations: dropping `gave_up` / `failed` from the `_settle` check, removing the exclusions, creating
documents for all hashes, dropping the marker: all killed. Checks: `make lint` clean; full pytest
1812 passed, 1 skipped; `check_code_docs.py --strict` exit 0.
