# Spec: Web Article Details, Export, and Scheduled Auto-Update

## Context

Users can trigger updates and list news from the web UI/API, but cannot:
- retrieve full article payload (`summary`, `content`) from the web API,
- export collected news data from the web API,
- run periodic automatic updates on a schedule using the tuned runtime settings (`concurrency=20`, `full-text concurrency=8`).

The project already supports:
- manual update trigger via `POST /api/update/run`,
- update settings storage via `GET/PUT /api/update/settings`,
- article storage with deduplication by `url_canonical_hash`,
- MCP APIs that can return article content (`news.get`).

## Goals

1. Add a web API endpoint to fetch a single article with `summary` and `content`.
2. Add a web API export endpoint (JSON) for downloading article data.
3. Add a repeatable scheduled auto-update mechanism (cron-friendly) using runtime env/config defaults and recommended `20/8` concurrency settings.
4. Improve web UI usability for copying links and filtering by explicit date range.

## Non-Goals

- Building a full scheduler inside the FastAPI app process.
- CSV/Excel export in this scope (JSON export only).
- UI redesign for article details/export.
- Multi-node distributed locking for scheduled updates.

## Requirements

### R1. Web Article Details API

Add `GET /api/news/{article_id}` endpoint that returns:
- `article_id`
- `title`
- `summary`
- `content`
- `published_at`
- `rank_score`
- `url`
- `url_canonical`
- `source_id`
- `source_key`
- `source_name`

Behavior:
- `404` if article does not exist.
- Preserves existing auth middleware behavior (same protection as other `/api/*` routes).

### R2. Web Export API (JSON)

Add `GET /api/news/export` endpoint returning JSON download payload.

Query params (initial scope):
- `hours`
- `limit`
- `min_ai_relevance`
- `query`
- `days`
- `sort`
- optional `include_content` (default `false`)

Behavior:
- Uses same filtering semantics as `/api/news`.
- Returns downloadable JSON (e.g. `Content-Disposition: attachment; filename=...json`).
- Includes at least metadata fields from `/api/news`.
- If `include_content=true`, also includes `summary`, `content`, and original `url`.

### R3. Scheduled Auto-Update (Cron-Friendly)

Add a script/documented command for scheduled updates that:
- runs `ai-news fetch --once`,
- is safe for repeated cron execution,
- supports env-based tuning for:
  - `AINEWS_CONCURRENCY_LIMIT=20`
  - `AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT=8`
- writes logs to stdout/stderr (cron-compatible).

Minimum deliverables:
- `scripts/auto_update_once.sh` (or equivalent stable script),
- README section with example cron entry (`*/30 * * * *`).

Concurrency overlap expectations:
- If cron overlaps (previous run still active), DB dedup prevents article duplication.
- We should document that overlapping runs are not ideal and recommend avoiding overlap.

### R4. Web UI: Copy Visible Links to Clipboard

Add a UI action (button) on the main news page to copy links for the currently displayed news list to clipboard.

Behavior:
- Copies URLs for the currently rendered/filtered result set (same items visible in UI).
- Output format: one URL per line.
- Uses browser clipboard API with graceful error handling/message if copy is unavailable.

### R5. Date Range Filter in Web UI / API

Support filtering news by explicit date range:
- `date_from` (inclusive)
- `date_to` (inclusive)

Use cases:
- a single day (same `date_from` and `date_to`)
- arbitrary date interval

Behavior:
- Available from web UI controls.
- Propagates to web API request.
- If date range is provided, it overrides relative `hours` window filtering.
- Existing `query`, `limit`, `sort`, and `min_ai_relevance` still apply.

API compatibility:
- Extend `/api/news` (and `/api/news/export`) with optional date range query params.

## Acceptance Criteria

1. `/api/news/{id}` returns `content`/`summary` for an existing article and `404` for missing id.
2. `/api/news/export` returns valid JSON download and honors filters.
3. `include_content=true` includes `content` field in export items.
4. A cron-friendly script exists and runs `fetch --once` with env overrides.
5. README documents a 30-minute cron example using `20/8`.
6. Web UI can copy currently displayed links to clipboard (one per line).
7. Web UI supports `date_from/date_to` filtering (including single-day filtering).
8. Existing tests continue to pass; new tests cover new web endpoints and date-range filtering logic.

## Risks / Notes

- Export with `include_content=true` may produce large payloads.
- Cron overlap can cause extra load; dedup prevents duplicate article rows but not duplicate fetch work.
- Web update settings UI currently does not expose `rss_full_text_concurrency_limit`; cron/env path is the first delivery path.
- Date-range filtering should use clear timezone semantics (prefer article `published_at` UTC timestamps; UI date input should be documented/handled consistently).
