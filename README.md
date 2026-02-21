# AI News Collector

Spec-driven Python application for collecting fresh English-language AI news from configured RSS/HTML sources.

## Requirements

- Python 3.12+
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

### 1) Prepare server once

```bash
sudo mkdir -p /opt/ai-news
sudo chown "$USER":"$USER" /opt/ai-news
git clone https://github.com/Orlv-85/AI_PARSER.git /opt/ai-news
cd /opt/ai-news
cp deploy/.env.prod.example .env
```

Edit `.env` and set strong `POSTGRES_PASSWORD`.

### 2) Manual deploy command on server

```bash
cd /opt/ai-news
./scripts/deploy_prod.sh
```

What this does:
- starts/updates PostgreSQL container
- runs `alembic upgrade head`
- starts/updates app container
- runs retention cleanup (`ai-news prune --older-than-days 100` by default)
- verifies app health

If schema didn't change, migration step is a no-op.

### 3) Deploy via GitHub Action on tag

Create repository variables/secrets:
- `DEPLOY_HOST` (repo variable)
- `DEPLOY_USER` (repo variable)
- `DEPLOY_APP_DIR` (repo variable, optional, default `/opt/ai-news`)
- `DEPLOY_SSH_PRIVATE_KEY` (repo secret)

Then push a tag from `master`:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Workflow `.github/workflows/deploy-release.yml` will SSH to server and run deploy.

### 4) Maintenance and backups

Retention + VACUUM:

```bash
./scripts/db_maintenance.sh
```

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

### Top news

```bash
ai-news top --hours 24 --limit 30
```

### Search

```bash
ai-news search --query "gpt" --days 7
```

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
