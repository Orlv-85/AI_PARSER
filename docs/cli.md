# CLI Usage

## Upload and review sources in the web UI

Open `/admin` and choose **Onboarding**. Upload a JSON file, or paste JSON and
click **Import & check**. The app opens the latest batch automatically and checks
new candidates in the background. **Check this batch** can also review an older
batch. **Connect recommended** enables technically validated, recommended draft
sources; uncertain sources remain available for individual review. Use
**Update > Run update** afterward to collect news.

Supported JSON shapes are `{"sources": [{"name": "AI Blog", "type": "rss",
"url": "https://example.com/feed.xml"}]}` and a top-level array of source objects
or URL strings. Only source `url` fields are imported: evidence links,
`website_url`, replacements and unverified recommendations are ignored. Plain
URLs/Markdown remain supported. Limits: 200 JSON records and a 1 MB file.

Verification reads only the feed/list page (at most 1 MB, 10-second network
timeout, bounded redirects), never the article archive. Jev receives at most
five publication samples in a 6,000-character brief. Confident decisions use
Jev alone; uncertain cases receive a DeepSeek second opinion using the same
brief, with thinking disabled and a 400-token output limit. A batch makes at
most 50 DeepSeek requests. Missing keys, provider failures or insufficient
evidence leave manual review; a provider failure stops further calls to that
provider in the batch. Successful model reviews are reused for unchanged
evidence for seven days. Overlapping source families always require review.

This workflow uses existing `JEV_API_KEY` / `AINEWS_JEV_ENABLED` settings and
`DS_API_KEY`. The second-opinion model is configured by
`AINEWS_SOURCE_REVIEW_DEEPSEEK_MODEL` (default `deepseek-flash`). Keys stay on the
server. Completed candidate results persist across restarts; interrupted pending
work can be restarted with **Check this batch**.

## World news stream

```bash
ai-news world scan --date 2026-10-31 --max-files 3     # counts only, writes nothing
ai-news world collect --date 2026-10-31 --max-files 3  # stores candidates; default date is yesterday UTC
```

```bash
ai-news world screen --date 2026-10-31 [--dry-run]   # Jev title screen, then FR-001 for the top with text (paid)
ai-news world texts --date 2026-10-31 [--dry-run]    # page text of the top screened-in stories, no key
ai-news world report --date 2026-10-31               # read-only first days check (JSON)
```

`scan` and `collect` download GDELT files. `collect` skips files that are already done and prints one
JSON summary. `report` writes nothing: use its output for `specs/018-daily-inference/records/world-days-<date>.md`.
Behavior: `src/app/core/world/world.md`; the nightly job: `docs/deploy.md`.

## Show configured sources

```bash
ai-news sources
```

## Fetch once

```bash
ai-news fetch --once
```

## Cron-friendly auto-update (every 30 minutes)

Use the helper script for repeated cron runs. It defaults to the tuned settings
`AINEWS_CONCURRENCY_LIMIT=10`, `AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT=4`,
and disables RSS full-text extraction by default with
`AINEWS_RSS_EXTRACT_FULL_TEXT=0`. You can override them via environment variables.

```bash
chmod +x scripts/auto_update_once.sh
./scripts/auto_update_once.sh
```

Example `crontab` entry (adjust paths/venv as needed):

```cron
*/30 * * * * cd /opt/ai-news && \
  . /opt/ai-news/venv1/bin/activate && \
  AINEWS_CONCURRENCY_LIMIT=10 \
  AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT=4 \
  AINEWS_RSS_EXTRACT_FULL_TEXT=0 \
  /opt/ai-news/scripts/auto_update_once.sh >> /var/log/ai-news-auto-update.log 2>&1
```

Notes:
- The script writes logs to stdout/stderr (cron-compatible).
- Overlapping cron runs are not ideal (extra fetch work/load). Article deduplication prevents duplicate rows, but prefer schedules that avoid overlap.
- `scripts/deploy_prod.sh` schedules the daily fetch on the server (`AUTO_UPDATE_ENABLED=1` by default; `0` disables it). With the default `AINEWS_DAILY_SCHEDULER=systemd` the fetch runs from the `ai-news-daily-fetch.timer` systemd timer (`scripts/install_daily_timers.sh`) and the managed cron block is removed; with `AINEWS_DAILY_SCHEDULER=cron` it installs a managed cron entry (`AUTO_UPDATE_CRON_SCHEDULE`, default `0 1 * * *`) using Docker Compose + `10/4`, with RSS full-text extraction disabled by default for cron (`AUTO_UPDATE_RSS_EXTRACT_FULL_TEXT=0`).
- Deploy-time cron knobs: `AUTO_UPDATE_ENABLED`, `AUTO_UPDATE_CRON_SCHEDULE`, `AUTO_UPDATE_LOG_PATH`, `AUTO_UPDATE_CONCURRENCY_LIMIT`, `AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT`, `AUTO_UPDATE_RSS_EXTRACT_FULL_TEXT`.

## Fetch optimization rollout (recommended for production)

Safe defaults now favor stability on a small VPS:

- Keep RSS full-text extraction disabled unless you are debugging extraction quality.
- Start with conservative concurrency (`10/4`) and increase only after measuring a full run.
- Keep cron auto-update disabled by default; prefer manual/UI-triggered runs until the source set is stable.
- Keep `update_execution_mode=thread` as the default web setting; switch to `process` only when you need to isolate a long-running web-triggered update from the request-serving process.
- Enable `article_batch_upsert_enabled` only after verifying the database path on staging or a controlled production window.

Recommended starting values for the new runtime knobs:

- `fetch_http_max_connections=20`
- `fetch_http_max_keepalive_connections=10`
- `rss_known_streak_stop=20`
- `html_known_streak_stop=20`
- `html_max_links_per_source=50`
- `article_batch_upsert_enabled=false`
- `fetch_emit_source_metrics=true`

Suggested rollout order:

1. Run with source metrics enabled and batch upsert disabled.
2. Watch a few update runs and confirm `not_modified_sources`, `skipped_known_html_links`, `early_stop_hits`, and total duration move in the expected direction.
3. If the app stays stable, enable `article_batch_upsert_enabled` and repeat the same checks.
4. Only after that, consider increasing concurrency or relaxing `html_max_links_per_source`.

Fast rollback toggles if an update regresses:

- disable `article_batch_upsert_enabled`
- lower `concurrency_limit`
- lower `html_max_links_per_source`
- set `rss_known_streak_stop=0` or `html_known_streak_stop=0` to disable early-stop logic
- keep `fetch_emit_source_metrics=true` while investigating so the logs stay comparable

## Benchmark snapshot

Local fixture benchmark for HTML link extraction (`tests/fixtures/html/list_page.html`, 1000 iterations, Python 3.14.2, `venv1`):

- `lxml`: `0.0413s`
- `selectolax`: `0.0341s`
- measured speedup: `1.21x`

This is a parser micro-benchmark, not a full end-to-end fetch run, but it is stable and reproducible for before/after comparisons of the hot link-extraction path.

## Top news

```bash
ai-news top --hours 24 --limit 30
```

## Search

```bash
ai-news search --query "gpt" --days 7
```

## Prune old news

```bash
ai-news prune --older-than-days 800
ai-news prune --older-than-days 800 --dry-run
```
