# Prompt: off-site database backups (B1, 2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first (especially "Deploy And Ops"). Work in a separate git worktree from
`origin/master`; other sessions may work in the main folder. Production is reached with
`ssh ai-news` and is **read-only for you**: any change on the server (install, config, timer,
upload, restore) needs the owner's explicit yes for that action.

## Context (verified by the coordinator on 2026-10-21)

- `.github/workflows/db-maintenance.yml` runs daily (cron `20 2 * * *`, GitHub starts it around
  07:00-08:00 UTC) and calls `scripts/db_maintenance.sh` and `scripts/db_backup.sh` over SSH.
- `scripts/db_backup.sh` writes `pg_dump | gzip` to `/opt/ai-news/backups/postgres_<UTC>.sql.gz`
  and deletes copies older than `BACKUP_RETENTION_DAYS` (14). About 49 MB per copy, 16 copies now;
  server disk 25 GB, 7.1 GB free.
- Every copy lives on the same VPS: losing the server loses all history (articles since 2024,
  digests, signals, admission ledger). Backlog item: `docs/backlog/article-archive-todo.json` task
  A0, `docs/backlog/backlog-todo.json` B1.
- Other backup files exist under `/opt/ai-news/backups/` (for example
  `reenrich-final-20261011/`); list them and say whether they need an off-site copy too.

## Part A: options and plan (stop after it and report)

Write `docs/plan-offsite-backups-2026-10-21.md`:
- Two or three off-site targets with current prices (check the providers' pricing pages; cite
  them with the date): for example Backblaze B2, Cloudflare R2, Hetzner Storage Box, or a pull to
  the owner's Mac. For each: monthly cost at 30 daily + 12 monthly copies of ~50 MB (and at 3x
  growth), egress cost of one full restore, what the owner must create (account, bucket, key),
  where credentials live (GitHub secret or server `.env`, never in the repo), and failure modes.
- Encryption before upload (for example `age` with a public key on the server and the private key
  kept by the owner off the server); what happens if the owner loses the key.
- Where the upload runs: after `db_backup.sh` in the same workflow step, or a timer on the server;
  tool (`rclone`, provider CLI, or `curl` to an S3 API) and how it is installed reproducibly.
- Retention off-site (daily 30, monthly 12 unless you argue otherwise) and how it is enforced.
- Alerting: how a failed upload becomes visible (failed workflow run at least).
- A restore test plan that does not touch production data: download, decrypt, restore into a
  throwaway PostgreSQL (locally or a separate container), compare row counts with production.
- Your recommendation and why.

Then stop. In your reply give the owner one question with a recommendation, for example:
"Хранилище: Cloudflare R2, ~$0.00/мес до 10 ГБ, ключ шифрования храните вы? (рекомендую да)",
plus the list of what the owner must create. This is a money question: wait for the answer.

## Part B: after the owner's answer (same session)

- One PR: the upload step (script and workflow change), retention, docs in `docs/deploy.md`
  (operator section: how to restore from the off-site copy), a troubleshooting case if you hit a
  non-obvious failure. Shell syntax check (`bash -n`), the workflow validated (`actionlint` if
  available). Do not merge.
- Server changes (installing a tool, adding a secret to `.env`) and the first real upload: list
  them as exact commands for the owner's yes, one action per line; run each only after the yes.
- Restore test from the off-site copy after the first upload, with the result in the PR.

## Output

- Part A: the plan file path (commit it in the PR branch), the question for the owner, the
  owner's to-do list.
- Part B: the PR link, the server actions done (each with the owner's yes), the restore test
  result, exact checks; open questions one line each (how settled, or a yes/no question for the
  owner with a recommendation).
- Save any prompt you write for another session to a file per `AGENTS.md`.
