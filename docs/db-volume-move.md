# Move the production database to the named volume

One-time server runbook (prepared 2026-10-31). Run it once, as root on the server (`ssh ai-news`),
then archive this file to `docs/archive/<YYYY-MM>/`.

## Why

- `docker-compose.prod.yml` mounted the named volume `pgdata` at `/var/lib/postgresql/data`. That
  is the path of PostgreSQL 17 and older.
- The `postgres:18-alpine` image keeps its data in `PGDATA=/var/lib/postgresql/18/docker` and
  declares `VOLUME /var/lib/postgresql`. Nothing was mounted there, so Docker created an
  **anonymous** volume for it (`e8d276e8...`, 278 MB) and the real database lives in that one.
  The named volume `ai-news_pgdata` (compose project `ai-news`) is mounted but empty and unused.
  Checked on the server 2026-10-31 with `docker inspect ai-news-db` and `docker volume ls`.
  The move procedure (copy with `cp -a`, start on the named volume, same row count) was rehearsed
  on a local throwaway `postgres:18-alpine`.
- Risk of leaving it: the database is on a volume without a name. `docker volume prune`,
  `docker system prune --volumes` or `docker compose down -v` after the container is gone delete
  it, and nothing in `docker volume ls` says it holds the data. A future major upgrade with
  `pg_upgrade` also needs the data root `/var/lib/postgresql` on one volume.
- Fix: mount `pgdata` at `/var/lib/postgresql` (the compose change in the same PR).

## Rules

- **Freeze deploys.** From step 1 until the PR is merged (step 10) nobody pushes a `v*` tag or
  runs `deploy-by-tag`. A deploy of the new compose before the move, or of the old compose after
  it, starts the database on an empty volume: the app would run migrations on an empty database.
  (The data is not lost, it stays on the other volume, but the site shows nothing until fixed.)
- The old anonymous volume is never touched or deleted by this runbook. It is the rollback copy.
- Do not run `docker volume prune` or `docker system prune --volumes` until step 11.

## Window and downtime

- Best window: **05:00-07:00 UTC** (07:00-09:00 EET), ideally a Sunday. Nightly jobs are done by
  about 02:15 UTC (fetch 01:00, digest 02:00, archive 03:00; the 4 h fetch limit is never
  reached), and the GitHub `db-maintenance` workflow, which runs `docker compose exec db`, was
  observed at about 08:30 UTC. Do not run it 01:00-04:00 UTC or around 08:00-09:00 UTC.
- Downtime of the site and API: about 6-10 minutes (app stopped in step 3 until step 8:
  dump 1-2 min, copy under 1 min, database start 30 s, checks). Caddy stays up and answers 502.
  Readers lose nothing; no job runs in the window.

## Steps

Use one shell on the server in `/opt/ai-news`.

```bash
cd /opt/ai-news
OLD=e8d276e81f1d3e4ab33f3b9d91abc8ee87e39590cc3fce9223480f599785b879
```

### 0. Before the window (no downtime)

```bash
docker inspect ai-news-db --format '{{range .Mounts}}{{.Name}} -> {{.Destination}}{{"\n"}}{{end}}'
# expect: $OLD -> /var/lib/postgresql   and   ai-news_pgdata -> /var/lib/postgresql/data
docker run --rm -v ai-news_pgdata:/v postgres:18-alpine ls -A /v        # expect: empty output
docker run --rm -v "$OLD":/v:ro postgres:18-alpine cat /v/18/docker/PG_VERSION   # expect: 18
df -h / | tail -1                                                       # expect: several GB free
gh run list --limit 3    # or the Actions page: no deploy in progress
```

Stop if any expectation fails. Make sure the off-site backup is fresh (`docs/deploy.md`,
"Off-site backups"); step 4 adds one more copy.

### 1. Put the new compose file next to the old one

The compose change is in the PR branch `fix/db-named-volume`; the file is taken from there, so the
move does not wait for the merge. The extra file is untracked, so a later `git checkout` keeps it.

```bash
git fetch origin fix/db-named-volume
git show origin/fix/db-named-volume:docker-compose.prod.yml > docker-compose.pgvolume.yml
diff docker-compose.prod.yml docker-compose.pgvolume.yml    # only the db volume line and its comment differ
docker compose -p ai-news -f docker-compose.pgvolume.yml config | grep -B1 -A3 'pgdata'
# expect: target: /var/lib/postgresql  (volume ai-news_pgdata)
```

### 2. Stop the nightly jobs

```bash
systemctl stop ai-news-daily-fetch.timer ai-news-daily-digest.timer ai-news-daily-archive.timer
systemctl is-active ai-news-daily-fetch.service ai-news-daily-digest.service ai-news-daily-archive.service   # inactive x3
docker ps --format '{{.Names}}'     # only ai-news-app, ai-news-db, ai-news-caddy and the two amnezia containers
```

If a job container is running, wait for it; do not stop it half-way.

### 3. Stop the app (downtime starts)

```bash
docker stop ai-news-app
```

### 4. Back up and record row counts

```bash
./scripts/db_backup.sh                      # prints the file; refuses an incomplete dump
ls -t backups/postgres_*.sql.gz | head -1
./scripts/db_table_counts.sh > /root/counts.before
wc -l /root/counts.before                   # about 25 tables
```

Copy the dump off the server, from the operator machine, and compare checksums:

```bash
scp ai-news:/opt/ai-news/backups/postgres_<TIMESTAMP>.sql.gz ~/Backups/
sha256sum ~/Backups/postgres_<TIMESTAMP>.sql.gz; ssh ai-news sha256sum /opt/ai-news/backups/postgres_<TIMESTAMP>.sql.gz
```

### 5. Stop the database cleanly

```bash
docker stop -t 60 ai-news-db
docker logs --tail 3 ai-news-db      # expect: database system is shut down
```

### 6. Copy the data into the named volume

`cp -a` keeps owner (uid 70, postgres) and mode 0700.

```bash
docker run --rm -v "$OLD":/from:ro -v ai-news_pgdata:/to postgres:18-alpine \
  sh -c 'cp -a /from/. /to/ && diff -rq /from /to && echo COPY_IDENTICAL && du -sb /from /to && cat /to/18/docker/PG_VERSION'
```

Expect `COPY_IDENTICAL`, equal sizes and `18`. Anything else: go to Rollback A.

### 7. Start the database on the named volume

```bash
docker compose -p ai-news -f docker-compose.pgvolume.yml up -d db
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai-news-db)" = healthy ]; do sleep 3; done
docker inspect ai-news-db --format '{{range .Mounts}}{{.Name}} -> {{.Destination}}{{"\n"}}{{end}}'
# expect exactly one line: ai-news_pgdata -> /var/lib/postgresql   (no anonymous volume)
```

### 8. Verify, then start the app (downtime ends)

```bash
./scripts/db_table_counts.sh > /root/counts.after
diff /root/counts.before /root/counts.after && echo COUNTS_IDENTICAL
docker exec ai-news-db psql -U ainews -d ainews -tAc 'select version_num from alembic_version'
docker start ai-news-app
sleep 10
docker exec ai-news-app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3).status)"   # 200
curl -fsS https://5kzt.l.time4vps.cloud/health
```

`COUNTS_IDENTICAL` is required (nothing wrote since step 3). Otherwise go to Rollback B.

### 9. Restart the jobs

```bash
systemctl start ai-news-daily-fetch.timer ai-news-daily-digest.timer ai-news-daily-archive.timer
systemctl list-timers 'ai-news-daily-*' --no-pager
```

### 10. Merge the PR and release

Only now: merge the PR with the compose change, and release as usual (`v*` tag). The deploy's
`up -d db` finds the same definition and keeps the container; if it recreates it, the data stays
(same named volume). Then remove the helper file: `rm /opt/ai-news/docker-compose.pgvolume.yml`.
After that deploy check once more: `docker inspect ai-news-db` shows only `ai-news_pgdata`.

### 11. Remove the old volume (7 days later, owner OK)

Keep `$OLD` for at least a week. Then, with a fresh backup on hand:

```bash
docker volume ls -f dangling=true       # $OLD must be listed there and nowhere in use
docker volume rm "$OLD"
```

## Rollback

- **A. Failure before step 7** (copy mismatch, anything odd): the old container and volume are
  intact. `docker start ai-news-db ai-news-app`, restart the timers (step 9). To retry later,
  empty the named volume first:
  `docker run --rm -v ai-news_pgdata:/v postgres:18-alpine sh -c 'rm -rf /v/* /v/.[!.]*'`.
- **B. Failure at step 8 (counts differ, database does not start):** the old volume was only read.
  Stop and remove the new container and run PostgreSQL on the old volume under the same network
  alias, then start the app:
  ```bash
  docker stop ai-news-app; docker rm -f ai-news-db
  docker run -d --name ai-news-db --restart unless-stopped --network ai-news_default \
    --network-alias db -v "$OLD":/var/lib/postgresql postgres:18-alpine
  docker start ai-news-app
  ```
  This is the pre-move state (data as of step 3). Later `docker compose up -d db` recreates the
  container with the compose definition; do not deploy until the cause is found.
- **C. After the app has run on the new volume:** the old volume is stale (it lacks the new
  writes). Roll back with a fresh `pg_dump` of the new database (`./scripts/db_backup.sh`), not
  with the old volume.
- **D. Both volumes unusable:** restore the dump from step 4 (or the off-site copy) into an empty
  named volume: empty it (Rollback A), `docker compose -p ai-news -f docker-compose.pgvolume.yml
  up -d db`, then
  `gunzip -c backups/postgres_<TIMESTAMP>.sql.gz | docker exec -i ai-news-db psql -q -v ON_ERROR_STOP=1 -U ainews -d ainews`
  and compare with `/root/counts.before`.

## If the compose change is deployed too early

Symptom: after a deploy the site shows no articles and `./scripts/db_table_counts.sh` shows empty
tables. The data is still on `$OLD`. Do not run anything that deletes volumes. Stop the app, stop
the new db container, and use Rollback B to bring the old database back, then empty the named volume (Rollback A) and run this runbook.
