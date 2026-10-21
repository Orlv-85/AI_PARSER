#!/usr/bin/env bash
# Encrypts one local pg_dump copy with age and uploads it to Backblaze B2 with rclone.
# Runs on the GitHub runner (.github/workflows/db-maintenance.yml), not on the server.
# Usage: scripts/db_offsite_upload.sh <path/postgres_<UTC>.sql.gz>
# Env: OFFSITE_B2_KEY_ID, OFFSITE_B2_APPLICATION_KEY, OFFSITE_B2_BUCKET, BACKUP_AGE_RECIPIENT.
# Retention of daily/ and monthly/ is enforced by the bucket's lifecycle rules, not here.
set -euo pipefail

BACKUP_MIN_BYTES="${BACKUP_MIN_BYTES:-1000000}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-26}"

dump="${1:?usage: db_offsite_upload.sh <postgres_<UTC>.sql.gz>}"
: "${OFFSITE_B2_KEY_ID:?missing}" "${OFFSITE_B2_APPLICATION_KEY:?missing}"
: "${OFFSITE_B2_BUCKET:?missing}" "${BACKUP_AGE_RECIPIENT:?missing}"

name="$(basename "$dump")"
stamp="$(printf '%s' "$name" | sed -n 's/^postgres_\([0-9]\{8\}T[0-9]\{6\}Z\)\.sql\.gz$/\1/p')"
if [ -z "$stamp" ]; then
  echo "Unexpected backup name: ${name}" >&2
  exit 1
fi

# Refuse a stale copy: the newest file on the server is old when today's backup did not run.
dump_epoch="$(date -u -d "${stamp:0:4}-${stamp:4:2}-${stamp:6:2}T${stamp:9:2}:${stamp:11:2}:${stamp:13:2}Z" +%s)"
age_hours=$(( ($(date -u +%s) - dump_epoch) / 3600 ))
if [ "$age_hours" -gt "$BACKUP_MAX_AGE_HOURS" ]; then
  echo "Backup ${name} is ${age_hours}h old (max ${BACKUP_MAX_AGE_HOURS}h)" >&2
  exit 1
fi

size="$(wc -c < "$dump" | tr -d ' ')"
if [ "$size" -lt "$BACKUP_MIN_BYTES" ]; then
  echo "Backup ${name} is too small: ${size} bytes" >&2
  exit 1
fi
gzip -t "$dump"
# pg_dump writes this footer last; a dump cut short (pg_dump failed mid-pipe) lacks it.
if ! gzip -cd "$dump" | tail -n 10 | grep -q -- '-- PostgreSQL database dump complete'; then
  echo "Backup ${name} is incomplete (no pg_dump footer)" >&2
  exit 1
fi

encrypted="${dump}.age"
age -r "$BACKUP_AGE_RECIPIENT" -o "$encrypted" "$dump"

export RCLONE_CONFIG_OFFSITE_TYPE=b2
export RCLONE_CONFIG_OFFSITE_ACCOUNT="$OFFSITE_B2_KEY_ID"
export RCLONE_CONFIG_OFFSITE_KEY="$OFFSITE_B2_APPLICATION_KEY"
remote="offsite:${OFFSITE_B2_BUCKET}"

# copyto checks size and SHA-1 of the uploaded object against the local file.
rclone copyto "$encrypted" "${remote}/daily/${name}.age"
echo "Uploaded daily/${name}.age ($(wc -c < "$encrypted" | tr -d ' ') bytes)"

# One monthly copy: the first successful upload of the month, so a missed day 1 is caught later.
month="${stamp:0:6}"
# Listing the bucket root, not monthly/: an empty prefix is "directory not found" for rclone.
monthly_existing="$(rclone lsf -R --files-only "${remote}" --include "/monthly/postgres_${month}*")"
if [ -z "$monthly_existing" ]; then
  rclone copyto "$encrypted" "${remote}/monthly/${name}.age"
  echo "Uploaded monthly/${name}.age"
fi

rm -f "$encrypted"
