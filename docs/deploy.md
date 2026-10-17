# Docker And Production Deploy

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
