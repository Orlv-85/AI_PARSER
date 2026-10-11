# AI News Collector

Spec-driven Python application for collecting fresh English-language AI news from configured RSS/HTML sources.

## Requirements

- Python 3.14.x (project target)
- SQLite (bundled with Python)
- `pip` or `uv`

## Installation

```bash
python -m venv venv1
source venv1/bin/activate
pip install -e ".[dev]"
```

## Run In Docker

### Build image

```bash
docker build -f build/Dockerfile -t ai-news-collector:latest .
```

To mirror the release workflow with a reusable dependency base:

```bash
DEP_HASH="$(./scripts/docker_dependency_fingerprint.sh)"
docker build -f build/Dockerfile --target runtime-base -t "ai-news-runtime-base:${DEP_HASH}" .
docker build \
  -f build/Dockerfile.runtime \
  --build-arg "RUNTIME_BASE_IMAGE=ai-news-runtime-base:${DEP_HASH}" \
  -t ai-news-collector:latest .
```

### Run container

```bash
mkdir -p data
docker run -d \
  --name ai-news \
  -p 8010:8010 \
  -e AINEWS_DATABASE_URL="sqlite:///./data/ai_news.db" \
  -e AINEWS_SOURCES_PATH="/app/sources.yaml" \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/sources.yaml:/app/sources.yaml:ro" \
  ai-news-collector:latest
```

### Run with Docker Compose

```bash
mkdir -p data
docker compose up -d --build
```

## Production Deploy (PostgreSQL + Git Tags)

### CI/CD trigger matrix

- push to any branch: `.github/workflows/tests.yml` (tests only, no deploy)
- push tag `v*`: `.github/workflows/deploy-release.yml` (tests, then deploy only on green)
- manual rollback/deploy by tag: `.github/workflows/deploy-by-tag.yml` (`workflow_dispatch`, input `deploy_tag`)
- nightly maintenance: `.github/workflows/db-maintenance.yml` (DB maintenance + backup over SSH)

### Required GitHub repo configuration

Repository Variables:
- `DEPLOY_HOST` (example: `5kzt.l.time4vps.cloud`)
- `DEPLOY_USER` (example: `root`)
- `DEPLOY_APP_DIR` (optional, default `/opt/ai-news`)
- `AINEWS_AUTH_USERNAME` (optional, default `operator`)
- `AINEWS_AUTH_ENABLED` (optional, default `true`)
- `AINEWS_AUTH_SESSION_TTL_SECONDS` (optional, default `3600`)
- `AINEWS_AUTH_COOKIE_SECURE` (optional, default `true`)
- `AINEWS_MCP_AUTH_ENABLED` (optional, default `false`)

Repository Secrets:
- `DS_API_KEY` (DeepSeek key, required for digest generation)
- `SERVER_PASSWORD`
- `AINEWS_AUTH_PASSWORD_HASH`
- `AINEWS_AUTH_SECRET`
- `AINEWS_MCP_AUTH_TOKEN` (required if `AINEWS_MCP_AUTH_ENABLED=true`)

### 1) Prepare server once

```bash
sudo mkdir -p /opt/ai-news
sudo chown "$USER":"$USER" /opt/ai-news
git clone https://github.com/Orlv-85/AI_PARSER.git /opt/ai-news
cd /opt/ai-news
cp deploy/.env.prod.example .env
```

Edit `.env` and set strong `POSTGRES_PASSWORD`.
Set `CADDY_SITE_ADDRESS` to your public domain/host (for example `5kzt.l.time4vps.cloud`).

### Daily digest generation (DeepSeek)

Set `DS_API_KEY` in the server's `.env` or in the job environment. Do not commit
the key. The scheduled daily job calls DeepSeek directly from Python, without
an external agent runner. The key is passed only in the HTTP Authorization
header, not in CLI arguments.

- Daily providers: the validated ten-topic JEV rubric and `deepseek-flash`.
- Run/rebuild a date: `./scripts/run_daily_digest_job.sh 2026-10-03`.
- The scheduled wrapper uses the released image from `.last_deploy_image` and
  runs `ai-news daily-publish` inside compose. The worker selects the complete
  stored UTC day, including more than 200 records, and uses a persistent private
  source cache and provider journal under `data/daily-enrichment/`.
- Summaries require complete JSON, exact supporting quotes, English semantic
  support review, at most 80 words and 400 characters. The worker permits one
  narrow repair, preserves usage/cost, and reuses validated summaries on resume.
- `AINEWS_DIGEST_ALLOW_FALLBACK` no longer enables excerpts in the scheduled path.
  Provider failure preserves the previous digest. Insufficient source/date or
  classification evidence is excluded with an explicit hold in the private
  daily report; `published_with_holds` is not full enrichment coverage.
- Daily safety caps are $1 JEV and $4 DeepSeek per report date; ordinary ingestion
  separately journals bounded JEV admission calls under `data/daily-admission/`.
- Deployment installs systemd timers at **01:00 UTC fetch** and **02:00 UTC
  publication**. Each publication processes the previous completed UTC date.
  Both jobs share the collector lock; publication waits for an active fetch.
  UTC calendar timers handle host DST without changing the server timezone.
  Installation removes the old managed daily cron blocks. Weekly stays off.
  Timers do not catch up on installation (`Persistent=false`); use the dated
  wrapper for an explicit resume. Logs are `logs/daily-fetch.log` and
  `logs/daily-digest.log`; inspect `systemctl list-timers 'ai-news-daily-*'`.
- The deploy retires the old proxy container without deleting its account data.
  Retired local tooling is moved to `backups/retired-ai-tools.*`, not reinstalled.
  The old proxy-provider CLI and external-agent job template are removed.

The tag deploy copies `DS_API_KEY` from GitHub Actions repository secrets into
the private server-side `.env`. A missing secret fails validation before any
server changes. Set the repository variable `AINEWS_DIGEST_MODEL` to override
the model. Manual server jobs can still use an exported key or the server `.env`.

Server prerequisites (once):
- Docker Engine + Docker Compose v2 installed and working for deploy user
- `git` installed
- outbound access to GitHub from server
- repository cloned into `${DEPLOY_APP_DIR}` (default `/opt/ai-news`)
- inbound ports `80/tcp` and `443/tcp` open in firewall/security group

### 2) Manual deploy command on server

```bash
cd /opt/ai-news
./scripts/deploy_prod.sh
```

What this does:
- starts/updates PostgreSQL container
- runs `alembic upgrade head`
- starts/updates app container + Caddy reverse proxy (HTTPS)
  - tagged release builds use a reusable `runtime-base-<hash>` dependency image
  - dependency base hash is computed from `build/Dockerfile`, `build/Dockerfile.runtime`, `build/requirements*.txt`, and `pyproject.toml`
  - if that base image already exists in GHCR, CI builds only the thin app/code image
- runs retention cleanup (`ai-news prune --older-than-days 800` by default)
- deploy and maintenance use explicit `RETENTION_DAYS`, then the server `.env`,
  then the 800-day default; GitHub workflows persist and pass the repository
  `RETENTION_DAYS` variable (default 800) so deploys preserve the configured policy
- verifies app health

If schema didn't change, migration step is a no-op.

To force rebuild regardless of file changes:

```bash
FORCE_BUILD=1 ./scripts/deploy_prod.sh
```

### 3) Deploy via GitHub Action on tag

Create repository variables/secrets:
- `DEPLOY_HOST` (repo variable)
- `DEPLOY_USER` (repo variable)
- `DEPLOY_APP_DIR` (repo variable, optional, default `/opt/ai-news`)
- `SERVER_PASSWORD` (repo secret)
- `AINEWS_AUTH_PASSWORD_HASH` (repo secret)
- `AINEWS_AUTH_SECRET` (repo secret)
- `AINEWS_MCP_AUTH_TOKEN` (repo secret, required only when MCP auth enabled)

Notes:
- Deploy workflow authenticates by server password (`SERVER_PASSWORD`) via `sshpass`.
- Deploy workflow updates auth keys in server-side `.env` at `${DEPLOY_APP_DIR}` from secrets.
- Keep DB secrets (for example `POSTGRES_PASSWORD`) in server-side `.env`.

Then push a tag from `master`:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Workflow `.github/workflows/deploy-release.yml` will SSH to server and run deploy.

Rollback / manual deploy by tag:
- Use workflow `.github/workflows/deploy-by-tag.yml` (`Run workflow` in GitHub UI).
- Provide `deploy_tag` input (for example `v0.1.0` or `v0.2.3-rollback`).
- Workflow deploys exactly that tag to server.

### 4) Maintenance and backups

Retention + VACUUM:

```bash
./scripts/db_maintenance.sh
```

Size guardrails in `db_maintenance.sh`:
- if DB reaches `DB_MAX_SIZE_GB` (default `5`)
- retention is tightened in steps (`DB_RETENTION_STEP_DAYS`, default `7`)
- until DB is below `DB_TARGET_SIZE_GB` (default `4`) or retention reaches 1 day

Backup:

```bash
./scripts/db_backup.sh
```

Nightly maintenance workflow:
- `.github/workflows/db-maintenance.yml`
- runs DB maintenance and backup over SSH (same deploy credentials)

### Healthcheck

```bash
curl -fsS http://127.0.0.1:8010/health
curl -I https://<your-domain>/health
docker ps --filter name=ai-news
```

### Auto-start on reboot (systemd)

1. Copy project to server, for example into `/opt/ai-news`.
2. Install unit file:

```bash
sudo cp deploy/ai-news.service /etc/systemd/system/ai-news.service
```

3. If your path is not `/opt/ai-news`, update `WorkingDirectory`:

```bash
sudo systemctl edit --full ai-news.service
```

4. Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ai-news.service
```

5. Check status/logs:

```bash
sudo systemctl status ai-news.service
docker compose -f /opt/ai-news/docker-compose.yml logs -f
```

## Configuration

### 1) Environment variables

```bash
export AINEWS_DATABASE_URL="sqlite:///./data/ai_news.db"
export AINEWS_SOURCES_PATH="sources.yaml"
export AINEWS_REQUEST_TIMEOUT_SECONDS="15"
export AINEWS_MAX_RETRIES="3"
export AINEWS_PER_SOURCE_MIN_INTERVAL_SECONDS="1.0"
export AINEWS_RESPECT_ROBOTS_TXT="true"
```

Optional Jev relevance scoring runs after RSS/HTML text extraction and before
article persistence. Set these values in the repository root's private `.env`
or export them in the process environment:

```dotenv
JEV_API_KEY=your-typesafe-api-key
AINEWS_JEV_ENABLED=true
AINEWS_JEV_MODEL=jev-1.13.0
AINEWS_JEV_TIMEOUT_SECONDS=3
AINEWS_JEV_CATEGORY_MIN_CONFIDENCE=0.7
```

The same Jev request returns relevance and a primary thematic category from the
seven existing digest sections. Jev's relevance probability feeds the existing
ranking formula. Categories are saved only when confidence meets
`AINEWS_JEV_CATEGORY_MIN_CONFIDENCE` (default `0.7`). Uncertain, unknown, or
invalid categories fall back to existing digest rules, independently of relevance.
It does not generate summaries or discard articles by default. Optional
semantic admission is gated by `AINEWS_SEMANTIC_ADMISSION_ENABLED=true` and
requires JEV. When enabled, AI-screening outages pause collection for the cycle,
and unchecked candidates remain available for retry. AI-central news, research,
substantive reviews, tutorials and evergreen guides
are eligible. Advertising landings, About pages, non-AI topics and incidental
AI mentions are excluded. Admission is categorical; category confidence and
ranking probability are independent and do not act as admission thresholds.
Already accepted articles persist; unchecked candidates remain in a durable
ledger, and never fall back to keyword admission. The exact public notice is:
`News collection is paused because AI screening is unavailable. Admin: please
check the AI providers and configuration.` Without semantic admission, existing
keyword scoring remains the default. If JEV is disabled or the API fails while
admission is enabled, no keyword fallback is used. After an API failure, no more
JEV calls are made during that fetch cycle; the next cycle retries pending work.
Pending work is replayed before checking the current feed/list, including after
a 304 response or list rotation. Up to 50 pending candidates per source are
replayed per cycle. Rejects and insufficient-evidence decisions are cached until
the sent evidence, model, policy or prompt version changes. The pause notice
clears after a fresh successful assessment; empty or cache-only retries retain it.
Apply the Alembic migration before enabling admission on an existing database.
Confirmed exclusions from the HTML page filter settle their pending URL and do
not replay after a 304. Temporary loading/parsing failures remain pending.
Connections and repeated-text results are reused within each cycle. Only bounded
title/summary/content text is sent. The key is masked in settings and is never
included in fallback logs.

Production Compose passes the Jev key and settings from the server's private
`.env` into the app container. Configure `JEV_API_KEY` privately on the server.
Both deploy workflows enforce `AINEWS_JEV_ENABLED=true` and
`AINEWS_SEMANTIC_ADMISSION_ENABLED=true`; production Compose defaults both to true.
Missing keys or screening outages pause collection without keyword admission.
The deployment applies migrations before starting the app. Local application
settings still default to disabled. Compose also forwards
`AINEWS_SEMANTIC_ADMISSION_POLICY_VERSION` and
`AINEWS_SEMANTIC_ADMISSION_PROMPT_VERSION`; their defaults match `Settings`.
Change the relevant version when changing admission policy or prompt.

Stored categories and confidence are included in `/api/news`, the digest link
feed and exports when available. The news page supports filtering by category
and `sort=category` (existing category order, then rank and freshness).
Digest generation uses the stored category first, with keyword rules for old or
unclassified articles, and ranks articles inside each group. A failed or disabled
Jev run does not erase previously accepted categories. Old articles are not
automatically reclassified and existing published digests are not rewritten.

For an existing database, apply the additive migration before starting this code:

```bash
./venv1/bin/alembic upgrade head
```

To keep local tests independent of a configured live API, run them with
`AINEWS_JEV_ENABLED=false ./venv1/bin/pytest`.

### 2) Source list (`sources.yaml`)

Project includes a starter `sources.yaml` with RSS + HTML sources.

Source management model:
- The database is the primary operational source registry.
- `sources.yaml` is a bootstrap/import artifact and an optional deterministic export snapshot.
- Runtime onboarding/review should happen against DB-backed records; YAML remains useful for seed data, backups, and diffs.

Phase 4 interop helper commands:

```bash
python scripts/sources_onboarding_helper.py db-bootstrap --sources sources.yaml
python scripts/sources_onboarding_helper.py db-review --status draft
python scripts/sources_onboarding_helper.py db-validate --batch-id 1
python scripts/sources_onboarding_helper.py db-export --output tmp/approved_sources.snapshot.yaml
```

Source schema:

- `id`
- `name`
- `type`: `rss` or `html`
- `url`
- `enabled`
- `fetch_interval_minutes`
- `source_weight`
- `html` (required for `type: html`)

## CLI Usage

### Upload and review sources in the web UI

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

### Show configured sources

```bash
ai-news sources
```

### Fetch once

```bash
ai-news fetch --once
```

### Cron-friendly auto-update (every 30 minutes)

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
- `scripts/deploy_prod.sh` can install/update a managed cron entry automatically on the server (default disabled) using Docker Compose + `10/4`, with RSS full-text extraction disabled by default for cron (`AUTO_UPDATE_RSS_EXTRACT_FULL_TEXT=0`).
- Deploy-time cron knobs: `AUTO_UPDATE_ENABLED`, `AUTO_UPDATE_CRON_SCHEDULE`, `AUTO_UPDATE_LOG_PATH`, `AUTO_UPDATE_CONCURRENCY_LIMIT`, `AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT`, `AUTO_UPDATE_RSS_EXTRACT_FULL_TEXT`.

### Fetch optimization rollout (recommended for production)

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

### Benchmark snapshot

Local fixture benchmark for HTML link extraction (`tests/fixtures/html/list_page.html`, 1000 iterations, Python 3.14.2, `venv1`):

- `lxml`: `0.0413s`
- `selectolax`: `0.0341s`
- measured speedup: `1.21x`

This is a parser micro-benchmark, not a full end-to-end fetch run, but it is stable and reproducible for before/after comparisons of the hot link-extraction path.

### Top news

```bash
ai-news top --hours 24 --limit 30
```

### Search

```bash
ai-news search --query "gpt" --days 7
```

### Run MCP server (for agent clients)

```bash
ai-news mcp-serve
```

MCP authentication configuration:
- `AINEWS_MCP_AUTH_ENABLED=false` (default, backward-compatible local mode)
- `AINEWS_MCP_AUTH_ENABLED=true` (enforce token on all MCP tools)
- `AINEWS_MCP_AUTH_TOKEN=<strong-random-token>` (required when auth is enabled)

Recommended secure startup:

```bash
export AINEWS_MCP_AUTH_ENABLED=true
export AINEWS_MCP_AUTH_TOKEN="replace-with-long-random-token"
ai-news mcp-serve
```

If auth is enabled and token is missing/blank, startup fails fast.

Available MCP tools:
- `news.update`
- `news.update_status`
- `news.list`
- `news.get`

When MCP auth is enabled, pass `auth_token` in each tool call:
- `news.update(..., auth_token="...")`
- `news.update_status(auth_token="...")`
- `news.list(..., auth_token="...")`
- `news.get(article_id=..., auth_token="...")`

Auth audit logging:
- `mcp_auth_success` and `mcp_auth_failed` events are emitted.
- Raw tokens are never written to logs.

Typical agent flow:
1. Call `news.update` (`wait=false` for async or `wait=true` for blocking mode).
2. Poll `news.update_status` until `finished`/`failed`.
3. Call `news.list` to get dataset slice.
4. Call `news.get` for full plain-text article content.

### Prune old news

```bash
ai-news prune --older-than-days 800
ai-news prune --older-than-days 800 --dry-run
```

## What the MVP does

- Ingests RSS and HTML sources.
- Normalizes content into a unified article model.
- Canonicalizes URLs and prevents duplicate inserts by canonical hash.
- Scores articles with freshness + AI relevance heuristics.
- Stores data in SQLite via SQLAlchemy and Alembic migrations.
- Supports PostgreSQL in production with Alembic migrations.
- Emits structured JSON logs for fetch runs.
- Exposes MCP tools for agent-driven update and analysis workflows.

## Weekly attention analytics v2

Both deploy workflows enforce `AINEWS_WEEKLY_V2_ENABLED=false`, and production
Compose defaults it to false. Deployments remove the managed weekly cron with
`AINEWS_WEEKLY_CRON_ENABLED=0`; the deploy script also defaults it to zero.
Repository variables cannot silently re-enable weekly during these deployments.
Local application settings still default to false. Any future reactivation must
explicitly change both the runtime flag and scheduling policy. It does not launch
a backfill. Runtime quality gates still suppress
confirmed labels when comparable coverage or classification is insufficient. Its arithmetic measures
publisher-balanced news attention, using complete observations rather than ranking.
The API keeps its existing fields and adds metrics, evidence, quality reasons and
immutable snapshot revisions. Manual/external reports remain `legacy`; a legacy POST
cannot overwrite a published v2 revision. GET only reads existing v2 snapshots and
never calls a model. Daily digest generation and ingestion ranking are unchanged.

Run additive migrations before collecting coverage with this version:

```bash
./venv1/bin/alembic upgrade head
```

Collection records publication provenance and scheduled source outcomes even with
v2 publication disabled and `AINEWS_FETCH_EMIT_SOURCE_METRICS=false`. Coverage requires
90% successful scheduled slots and six successful days per week. Empty feeds and
304 are successes; malformed feeds, unknown publication dates, incomplete HTML
collection and known truncation cannot prove healthy coverage. RSS observations are
preserved from the entire downloaded feed even when legacy ingestion stops early.
HTML publication metadata is recorded separately, without changing ingestion dates.
Existing article/alias discovery timestamps never establish verified history.

Publisher ownership overrides use `AINEWS_WEEKLY_PUBLISHER_OVERRIDES`, a JSON object
mapping domains to group IDs, for example `{"example.com":"owner","other.com":"owner"}`.
The fallback groups common registrable domains conservatively; review ownership and
unusual/public suffixes before release. Changes to grouping/configuration reset
comparability rather than silently rewriting historical coverage.

After establishing coverage and reviewing the taxonomy, run the v2 worker against
the same database as ingestion. The following invocation authorizes provider work
within the explicit per-run budgets shown; configure `JEV_API_KEY` and `DS_API_KEY`:

```bash
AINEWS_WEEKLY_V2_ENABLED=true \
AINEWS_WEEKLY_JEV_DECISION_BUDGET=1000 \
AINEWS_WEEKLY_AMBIGUITY_BUDGET=100 \
AINEWS_WEEKLY_NARRATIVE_BUDGET=16 \
./venv1/bin/ai-news weekly-analytics --report-date 2026-10-04 --limit 200
```

`--limit` is retained as a compatibility hint; it never limits counting. The input
safety cap is explicit (`AINEWS_WEEKLY_INPUT_SAFETY_CAP`, default 100000): hitting it
suppresses confirmed labels. Jobs freeze publication observations, cutoff, coverage,
taxonomy, thresholds and provider configuration. A unique input key and date-wide
publication lock prevent duplicate work and competing revisions. Expired leases
can resume; cached decisions persist across runs. `--enqueue-only` records work;
`--drain-only --max-jobs 8` processes pending/retry work. Provider budgets and the
900-second wall limit apply across the drain invocation, including retries.

Weekly model/prompt settings are `AINEWS_WEEKLY_JEV_MODEL`,
`AINEWS_WEEKLY_DEEPSEEK_MODEL` and `AINEWS_WEEKLY_PROMPT_VERSION`. Jev uses the existing
timeout setting. DeepSeek timeout defaults to 60 seconds; at most two transient
retries honor Retry-After. Input is conservatively bounded by prompt character count
against `AINEWS_WEEKLY_INPUT_TOKEN_CAP` (16000); DeepSeek output is capped by
`AINEWS_WEEKLY_OUTPUT_TOKEN_CAP` (1200). Calls/tokens/failures are recorded without keys.
Narrative failures retain metric-derived text and stored citations.

The existing `scripts/run_weekly_analytics_job.sh` detects the flag inside the app
container and drains this service, preserving cron cadence. Monday ingestion only
enqueues v2 work. Direct `digest_generator.py publish-feed-weekly` remains a legacy
adapter unless the host explicitly sets `AINEWS_WEEKLY_V2_ENABLED=true`; in that mode
it uses the local configured DB and the shared worker (its base-url stays accepted).

Export an eight-week comparison and deterministic manual review samples, without
provider calls:

```bash
./venv1/bin/ai-news weekly-analytics-audit --report-date 2026-10-04 \
  --weeks 8 --output tmp/weekly-review.json
```

The export includes section counts, rejected candidates/quality reasons, evidence,
up to 200 stratified assignments and 50 event pairs, and worker usage. It deliberately
does not certify precision without manual labels. Review multilingual, ambiguous
and unseen-topic examples, trace every displayed trend, and audit missed signals.
Separate tuning and evaluation weeks; freeze revised thresholds under a new
methodology version. Require the release criteria in
[trend-spec.md](specs/010-weekly-ai-analytics-for-management-dashboard/trend-spec.md).
If historical coverage is unavailable, collect two completed weeks for Up/Down and
35 observed days for New. Complete the replay and semantic review to assess trend
quality; enabling the runtime flag does not certify historical coverage or precision.

Explicit backfill creates new revisions; original legacy reports remain stored.
A failed or insufficient regeneration keeps the last ready revision. Rollback sets
the v2 flag to false while retaining evidence and snapshots; no destructive migration
is required. Unverified legacy publication cannot replace a date with a v2 snapshot.

## Article dates and one-time re-enrichment

Publication, modification and discovery are separate. Unknown publication
timestamps are `null`; known calendar dates remain available without an invented
time. News APIs also expose publication status/precision and optional material
type/comparison metadata. Migration `a42b750d0c44` is required for these fields.

See [the implementation and operator guide](docs/article-reenrichment.md) for
the module map, API changes, private cache, provider journal, apply/restore and
the limits of daily automation. The ten re-enrichment topics are readable and
filterable; the ordinary JEV rubric and daily digest process remain separate.
The completed data operation is recorded in
[the production report](docs/reenrich-production-results-2026-10-11.md).

## Development

```bash
ruff check .
pytest
```

## Troubleshooting

- `ModuleNotFoundError`: activate `venv1` and reinstall with `pip install -e ".[dev]"`.
- `sqlite3.OperationalError: unable to open database file`: create `data/` directory or fix `AINEWS_DATABASE_URL`.
- Empty `top` results: run `ai-news fetch --once` first and verify enabled sources in `sources.yaml`.
- Source fetch errors: check network access and source availability; fetch run logs include `source_id`, `stage`, `error_type`.

## Spec Artifacts

- `.specify/memory/constitution.md`
- `.specify/specs/001-ai-news-collector/spec.md`
- `.specify/specs/001-ai-news-collector/plan.md`
- `.specify/specs/001-ai-news-collector/tasks.md`

## Agent Architecture Notes

You do not need a separate repository for the agent that uses MCP.

Recommended setup:
- Keep parser + MCP server in this project/repo.
- Run analyst agent as a separate process/client (it connects to MCP and reads prepared article text).
- Share the same database/storage backend.

Create a separate project for the analyst only if you need:
- independent release cycle,
- different runtime/dependency stack,
- stricter security/isolation boundaries.
