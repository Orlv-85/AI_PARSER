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
- `OFFSITE_B2_BUCKET` (Backblaze B2 bucket for off-site backups)
- `BACKUP_AGE_RECIPIENT` (age public key `age1...`; the private key stays with the owner)

Repository Secrets:
- `DS_API_KEY` (DeepSeek key, required for digest generation)
- `SERVER_PASSWORD`
- `OFFSITE_B2_KEY_ID`, `OFFSITE_B2_APPLICATION_KEY` (B2 application key limited to the backup
  bucket, read and write)
- `AINEWS_AUTH_PASSWORD_HASH`
- `AINEWS_AUTH_SECRET`
- `AINEWS_PUBLISH_API_TOKEN` (optional; bearer token for machine POSTs of
  digests/weekly reports, at least 32 characters, `openssl rand -hex 32`.
  Empty or missing disables bearer auth, so only admin sessions can publish)

### 1) Prepare server once

```bash
sudo mkdir -p /opt/ai-news
sudo chown "$USER":"$USER" /opt/ai-news
git clone https://github.com/Orlv-85/AI_PARSER.git /opt/ai-news
cd /opt/ai-news
cp deploy/.env.prod.example .env
```

Edit `.env` and set strong `POSTGRES_PASSWORD`.
`AINEWS_PUBLISH_API_TOKEN` comes from the repository secret: both deploy
workflows write it to `.env` on every deploy, replacing any earlier line, so a
value edited by hand on the server is overwritten. To rotate or disable the token,
change the secret and redeploy (see
[Configuration](configuration.md#publish-api-token)).
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
- After a successful publication, the same locked job runs `ai-news daily-signals`
  for the same date with an outer `timeout` (at most 2700 s, less when the 4 h job
  budget is short). Signals never change the job result: a failure or timeout is
  logged and the container removed. Paid extraction is on by default in
  production; `AINEWS_DAILY_SIGNALS_ENABLED=false` in the server `.env` turns it off; see
  [Daily AI Signals](daily-signals.md).
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

`db_backup.sh` fails and removes the file when the dump lacks the pg_dump footer
(`-- PostgreSQL database dump complete`), so a failed `pg_dump` is not kept as a backup.

Nightly maintenance workflow:
- `.github/workflows/db-maintenance.yml`
- runs DB maintenance and backup over SSH (same deploy credentials)
- then copies the newest `backups/postgres_*.sql.gz` to the runner and runs
  `scripts/db_offsite_upload.sh`: checks the dump (age < 26 h, size, gzip, pg_dump footer),
  encrypts it with `age` to `BACKUP_AGE_RECIPIENT`, uploads it with `rclone` to B2
  `daily/<name>.age`, and to `monthly/` when the month has no copy yet
- a failed check or upload fails the run; GitHub mails failed scheduled runs. The repo is public:
  GitHub disables scheduled workflows after 60 days without repository activity - re-enable in
  the Actions tab if that happens

### Off-site backups (Backblaze B2)

- Bucket `OFFSITE_B2_BUCKET`, private. Retention by the bucket's lifecycle rules, not by our code:
  `daily/` 30 days, `monthly/` 365 days.
- Objects are `age`-encrypted; only the owner's private key decrypts them. Lost key = off-site
  copies unreadable (on-server copies, 14 days, are not affected).

Account, keys and limits (set up 2026-10-21):
- Bucket name: GitHub variable `OFFSITE_B2_BUCKET`. Lifecycle rules in the B2 console (Buckets ->
  bucket -> Lifecycle Settings): `daily/` hide after 30 days, `monthly/` hide after 365 days, both
  delete 1 day after hiding. Check them: `rclone backend lifecycle <remote>:<bucket>`.
- Keys: B2 application key in GitHub secrets `OFFSITE_B2_KEY_ID` / `OFFSITE_B2_APPLICATION_KEY`
  (the owner's local `.env` keeps a copy as `B2-KEY-ID` / `B2-APPLICATION-KEY`). age private key:
  `~/ai-news-backup.agekey` on the owner's Mac and a copy in the owner's password manager; its
  public part is the GitHub variable `BACKUP_AGE_RECIPIENT`.
- Caps (B2 console -> Caps & Alerts) are $0: storage 10 GB, download 1 GB/day; uploads are free.
  B2 mails the owner at 75% and 100%. At the cap B2 refuses new uploads instead of billing: the
  nightly run fails (GitHub mails), existing copies stay. Fix: shorten `daily/` / `monthly/` days
  in the lifecycle rules, or raise the storage cap (B2 storage is ~$0.007/GB-month).
- Changing retention needs no code change: only the lifecycle rules.

Restore test or real restore from the off-site copy, on the owner's machine (docker, `rclone`,
`age`; `brew install age rclone`), never on prod:

```bash
export OFFSITE_B2_KEY_ID=... OFFSITE_B2_APPLICATION_KEY=... OFFSITE_B2_BUCKET=...  # read-only key is enough
export BACKUP_AGE_IDENTITY=~/ai-news-backup.agekey
PROD_SSH=ai-news ./scripts/db_offsite_restore_test.sh            # newest daily/
./scripts/db_offsite_restore_test.sh monthly/postgres_<UTC>.sql.gz.age
```

It downloads and decrypts the copy, compares its sha256 with the server copy (when `PROD_SSH` is
set and the copy is still on the server), restores it into a throwaway `postgres:18-alpine`
container `ai-news-restore-test` with `ON_ERROR_STOP=1`, prints row counts per table and, with
`PROD_SSH`, the prod counts next to them (read-only `SELECT`; prod counts may only be larger).
The container and the plaintext dump are removed at exit.

For a real restore, decrypt the same way (`age -d -i <key> <file>.age > <file>`) and feed the
`.sql.gz` to `psql` of the target database; replacing prod data needs the owner's explicit yes.

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
