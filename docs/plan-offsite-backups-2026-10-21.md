# Plan: off-site database backups (B1 / A0, 2026-10-21)

Status: owner chose **Backblaze B2** on 2026-10-21; the age key is kept by the owner; the owner
keeps a copy of the server `.env` themselves. Part B implements the plan with B2 (section 9).
Prompt: `docs/prompt-offsite-backups-2026-10-21.md`.

## 1. What exists now (checked read-only on prod, 2026-10-21)

- Schedule: `.github/workflows/db-maintenance.yml` (cron `20 2 * * *`, starts ~07:00-08:00 UTC)
  runs `scripts/db_maintenance.sh && scripts/db_backup.sh` over SSH (sshpass, root). No server
  cron or systemd timer runs a backup (`crontab -l` empty; timers: only `ai-news-daily-fetch`,
  `ai-news-daily-digest`, system `dpkg-db-backup`).
- `scripts/db_backup.sh`: `pg_dump | gzip > backups/postgres_<UTC>.sql.gz`, deletes copies older
  than `BACKUP_RETENTION_DAYS` (server `.env`: 14). 16 copies (2026-10-06 .. 2026-10-21).
- Size: DB 139 MB; dump grew from 10 MB (2026-10-06) to 47 MB (2026-10-21), mostly re-enrichment
  data. Disk 25 GB, 7.1 GB free.
- Server: Ubuntu 24.04 x86_64; `gpg` and `curl` installed; `age`, `rclone`, `aws` not installed.
- **Defect found:** `db_backup.sh` runs under `sh -eu` without `pipefail`. If `pg_dump` fails
  (DB down, auth), `gzip` still succeeds and a truncated or empty `.sql.gz` is kept and reported as
  "Backup completed". Off-site upload would then ship a broken copy silently. Part B adds a check
  (dump ends with `-- PostgreSQL database dump complete`, `gzip -t` passes) before upload.

### Other files in `/opt/ai-news/backups/`

| Path | Size | What | Off-site? |
| --- | --- | --- | --- |
| `retired-ai-tools.HOvdBe/` | 1023 MB | old pocketpaw venv | No: software, reinstallable |
| `before_jev_october_20261010T102234Z.sql.gz` | 30 MB | full dump before JEV change (plain SQL despite `.gz`) | Yes, once (pre-change DB state; the daily copies of that date expire on ~2026-10-25) |
| `daily-publication-20261011/` | 23 MB | `full-before-release.dump` + job logs | Yes, once (full dump before release) |
| `reenrich-final-20261011/` | 312 MB | pre-apply dumps, rollback/apply JSON | Yes, once (rollback data of the re-enrichment run), without `env-before` (copy of server `.env`) |
| `legacy-jev-20261010T222433Z/` | 177 MB | pre-apply dump, journal, snapshots | Yes, once (rollback data of legacy JEV) |
| `reenrich-20261010T232951Z/`, `weekly-stage1-20261011/` | 59 + 116 MB | JSON snapshots | Yes, once (cheap; same reason) |
| `digests_before_jev_*`, `daily-cycle-20261012/` | < 1 MB | digest JSON, logs | Yes, once (tiny) |
| `semantic-admission-enable-*/server.env` | small | copy of server `.env` with secrets | No: secrets do not leave the server, even encrypted (see open questions) |

Secret check (coordinator, read-only, 2026-10-21): only `reenrich-final-20261011/env-before` and
`legacy-jev-*/retention-800/server.env` hold secrets; other matches are article text.

One-time archive: declined by the owner on 2026-10-21 (the pre-change snapshots are not needed);
not uploaded, no archive workflow.
The nine pre-change entries were then deleted from the server with the owner's yes (2026-10-21,
~720 MB); `retired-ai-tools.HOvdBe/` and `semantic-admission-enable-*/` were kept.

## 2. Targets and prices (pricing pages read 2026-10-21)

Volume: 30 daily + 12 monthly = 42 copies x ~50 MB = **~2.1 GB**; at 3x growth (~150 MB/copy)
**~6.3 GB**. Operations: ~5 requests/day.

| | Cloudflare R2 (Standard) | Backblaze B2 | Hetzner Storage Box BX11 | Pull to owner's Mac |
| --- | --- | --- | --- | --- |
| Price | $0.015/GB-mo, first 10 GB-mo free; Class A $4.50/M, B $0.36/M, 1M/10M free | $6.95/TB-mo (~$0.007/GB), first 10 GB free; class A-C calls free | EUR 3.20/mo excl. VAT for 1 TB, no minimum term | $0 |
| 2.1 GB / month | **$0** (free tier) | **$0** (free tier) | EUR 3.20 + VAT | $0 |
| 6.3 GB (3x) / month | **$0** (free tier; $0.10 without it) | **$0** (free tier; $0.04 without it) | EUR 3.20 + VAT | $0 |
| Egress, one full restore | $0 (egress always free) | $0 (free up to 3x avg stored; then $0.01/GB) | $0 (unlimited traffic) | n/a |
| Protocol | S3 API | S3 API (and B2 API) | SFTP/rsync/borg/restic/rclone, no S3 | SSH pull (`scp`) |
| Retention enforced by | bucket lifecycle rules per prefix; optional bucket lock | lifecycle rules per prefix; optional Object Lock | our script (no lifecycle); snapshots | our script on the Mac |
| Owner creates | Cloudflare account (payment method required to enable R2), bucket, R2 API token "Object Read & Write" limited to that bucket | B2 account, bucket (private), application key limited to that bucket | Storage Box order, SSH key / sub-account | launchd job, disk space |

Sources: https://developers.cloudflare.com/r2/pricing/ , https://www.backblaze.com/cloud-storage/pricing ,
https://www.hetzner.com/storage/storage-box/ (all read 2026-10-21; prices may change).

Failure modes per target:
- R2 / B2: wrong or expired token (upload fails -> workflow fails); account suspended for billing
  (card expired) - R2 needs a card on file even at $0; provider outage on the upload day (next day
  catches up, monthly copy logic tolerates a missed day); free tier changes (cost stays cents).
- B2 only: restores above 3x stored volume per month cost $0.01/GB (irrelevant at this size).
- Hetzner: fixed cost for 0.2% use of 1 TB; retention code is ours (bugs delete too much or too
  little); SFTP password/key on the runner.
- Mac pull: Mac asleep/off/travelling = no copy, and nobody notices unless the job reports; the
  Mac also needs root SSH to prod (already true) - so it is a second copy, not a primary one.

## 3. Encryption

- `age` with an X25519 key pair. The owner generates the key on the Mac
  (`age-keygen -o ~/ai-news-backup.agekey`), keeps the private key off the server (password
  manager + one offline copy), and gives only the public key (`age1...`) - stored as GitHub
  variable `BACKUP_AGE_RECIPIENT` (not secret: a public key is safe to show).
- Every object is `postgres_<UTC>.sql.gz.age`; the bucket and the provider see only ciphertext.
- Losing the private key = **all off-site copies are unreadable**; the on-server copies (14 days)
  are unaffected. Mitigation: two copies of the key in different places; the restore test (section
  7) proves the key works; optional second recipient (`-r` twice) for a backup key.
- Why `age`, not `gpg`: one static binary, one-line key, no keyring/trust state. `gpg` is already on
  the server, but encryption runs on the runner (section 4), so nothing is installed on the server.

## 4. Where the upload runs

Recommended: **a new step in `db-maintenance.yml`, on the GitHub runner**, after the backup step:

1. `scp` the newest `backups/postgres_*.sql.gz` from the server to the runner (same sshpass login
   as today; the file name is printed by `db_backup.sh`).
2. Verify: `gzip -t`, last line is `-- PostgreSQL database dump complete`, size > minimum.
3. `age -r "$BACKUP_AGE_RECIPIENT"` -> `.sql.gz.age`.
4. Upload to `daily/` with `rclone`; if `monthly/` has no object for the current month, copy it
   there too (so a missed 1st of the month is caught on the next run).
5. `rclone lsl` the uploaded object and compare its size.

Why the runner and not the server:
- Nothing is installed or configured on the production server (no `.env` change, no new timer).
- Bucket credentials live only in GitHub secrets; a compromised server cannot read or delete the
  off-site copies. The runner already has root on the server (`SERVER_PASSWORD`), so seeing the
  plaintext dump adds no new trust.
- Failures show up as a failed workflow run, which GitHub e-mails.
- The repo is public, so run logs are public: the step prints only object names and sizes, never
  keys, endpoints with account id, or dump content (secrets are masked by GitHub anyway).

Tools on the runner (`ubuntu-24.04`): `sudo apt-get install -y age rclone` (Ubuntu noble packages:
age 1.1.x, rclone 1.60.x; both support Cloudflare R2 / B2 via S3). rclone is configured only by
environment variables (`RCLONE_CONFIG_OFFSITE_TYPE=s3`, provider, endpoint, keys), no config file.
Alternative considered: AWS CLI (preinstalled on runners) - rejected because recent v2 versions
send default checksums that some S3-compatible providers reject; rclone handles that.

## 5. Retention off-site

- `daily/`: 30 days; `monthly/`: 12 months (365 days).
- Enforced by the **provider's lifecycle rules per prefix** (R2: object lifecycle "delete after N
  days"; B2: lifecycle rules per prefix), not by our code: deletion keeps working even if the
  workflow stops, and our script never needs delete rights in normal operation.
- Optional hardening (R2 bucket lock / B2 Object Lock on `daily/` for 7 days): a leaked token
  cannot delete recent copies. Recommended to add later, not in the first PR.
- On-server retention stays 14 days (`BACKUP_RETENTION_DAYS`), unchanged.

## 6. Alerting

- Any failed step (dump check, encrypt, upload, size compare) fails the workflow run; GitHub sends
  an e-mail to the owner for failed scheduled runs.
- Gap: the repo is public, and GitHub **disables scheduled workflows in public repositories after
  60 days without repository activity**; then no
  run and no failure mail. The repo is active daily now; Part B adds a line about it to
  `docs/deploy.md`. A freshness check from outside (for example, the weekly report checks the
  newest `daily/` object is < 36 h old) is a possible follow-up, not in this PR.

## 7. Restore test (no production data touched)

On the owner's Mac (or the runner in a manual `workflow_dispatch` job), never on prod:

1. `rclone copy offsite:<bucket>/daily/<newest>.sql.gz.age .`
2. `age -d -i ~/ai-news-backup.agekey <file> | gunzip > dump.sql`
3. `docker run -d --name ai-news-restore-test -e POSTGRES_PASSWORD=x -e POSTGRES_USER=ainews -e POSTGRES_DB=ainews postgres:18-alpine`
   (same major as prod: `postgres:18-alpine`), then `psql -U ainews -d ainews < dump.sql`
   with `ON_ERROR_STOP=1`.
4. Row counts of the main tables (`articles`, digests, signals, admission ledger and the rest from
   `pg_stat_user_tables` / `count(*)`) in the restored DB vs the same query on prod (read-only
   `SELECT` over `ssh ai-news`); counts must match the prod state at dump time (prod keeps growing,
   so compare with the on-server copy of the same dump if exact match is needed).
5. `docker rm -f ai-news-restore-test`; delete the plaintext dump.

Result goes into the PR description; the procedure goes into `docs/deploy.md` (operator section).

## 8. Recommendation

**Cloudflare R2**, with Backblaze B2 as an equal alternative:
- $0/month at today's and 3x volume (10 GB free tier), egress always free, so restores and restore
  tests never cost anything.
- S3 API + lifecycle rules per prefix + bucket lock: retention and protection without our code.
- Encryption with `age` on the runner, credentials in GitHub secrets, no change on the server.

Choose B2 instead if the owner prefers no card on file / already has a Backblaze account: same plan,
only the endpoint and key type differ. Hetzner costs money for no gain at this size; the Mac pull is
a useful second copy later, not the primary.

## 9. What the owner creates (B2, chosen)

1. Backblaze account (B2 Cloud Storage).
2. Private bucket (for example `ai-news-backups-<random>`; B2 bucket names are global), lifecycle
   rules: prefix `daily/` - hide after 30 days, delete 1 day after hiding; prefix `monthly/` -
   hide after 365 days, delete 1 day after hiding.
3. Application key "Read and Write", only that bucket -> `keyID` + `applicationKey` (shown once).
   A second "Read Only" key for the owner's machine (restore tests).
4. GitHub secrets `OFFSITE_B2_KEY_ID`, `OFFSITE_B2_APPLICATION_KEY`; variables `OFFSITE_B2_BUCKET`,
   `BACKUP_AGE_RECIPIENT`.
5. `age-keygen -o ~/ai-news-backup.agekey` on the Mac; private key into the password manager +
   offline copy; the `age1...` public key into `BACKUP_AGE_RECIPIENT`.

Implementation uses rclone's native `b2` backend (env-only config), not the S3 endpoint.

## 10. Part B scope (after the answer)

One PR, not merged: upload step in `db-maintenance.yml` + helper script (`scripts/db_offsite_upload.sh`),
dump completeness check (fix of the defect in section 1), `docs/deploy.md` operator section (restore
from off-site), `bash -n`, `actionlint`. Then, each with the owner's yes: first real upload
(`workflow_dispatch`), restore test; result in the PR.
