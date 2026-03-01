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
  - rebuilds image only when build inputs changed (`build/Dockerfile`, `Dockerfile`, `requirements*.txt`, `pyproject.toml`, `poetry.lock`)
  - otherwise runs `docker compose up -d app caddy` without rebuild
- runs retention cleanup (`ai-news prune --older-than-days 100` by default)
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
ai-news prune --older-than-days 100
ai-news prune --older-than-days 100 --dry-run
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
