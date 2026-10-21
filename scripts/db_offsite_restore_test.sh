#!/usr/bin/env bash
# Restore test of an off-site copy into a throwaway PostgreSQL container; never touches prod.
# Runs on the owner's machine (needs docker, rclone, age and the private age key).
# Usage: scripts/db_offsite_restore_test.sh [daily/postgres_<UTC>.sql.gz.age]  (default: newest daily)
# Env: OFFSITE_B2_KEY_ID, OFFSITE_B2_APPLICATION_KEY (read-only key is enough), OFFSITE_B2_BUCKET,
#      BACKUP_AGE_IDENTITY (private key file, default ~/ai-news-backup.agekey),
#      PROD_SSH (optional, e.g. ai-news: compare with the server copy and prod row counts, read-only).
set -euo pipefail

: "${OFFSITE_B2_KEY_ID:?missing}" "${OFFSITE_B2_APPLICATION_KEY:?missing}" "${OFFSITE_B2_BUCKET:?missing}"
BACKUP_AGE_IDENTITY="${BACKUP_AGE_IDENTITY:-$HOME/ai-news-backup.agekey}"
PROD_SSH="${PROD_SSH:-}"
PROD_APP_DIR="${PROD_APP_DIR:-/opt/ai-news}"
PG_IMAGE="${PG_IMAGE:-postgres:18-alpine}"
CONTAINER="ai-news-restore-test"

export RCLONE_CONFIG_OFFSITE_TYPE=b2
export RCLONE_CONFIG_OFFSITE_ACCOUNT="$OFFSITE_B2_KEY_ID"
export RCLONE_CONFIG_OFFSITE_KEY="$OFFSITE_B2_APPLICATION_KEY"
remote="offsite:${OFFSITE_B2_BUCKET}"

object="${1:-}"
if [ -z "$object" ]; then
  object="daily/$(rclone lsf "${remote}/daily/" --include 'postgres_*.sql.gz.age' | sort | tail -n 1)"
fi
name="$(basename "$object" .age)"

workdir="$(mktemp -d)"
cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$workdir"
}
trap cleanup EXIT

echo "Downloading ${object}"
rclone copyto "${remote}/${object}" "${workdir}/${name}.age"
age -d -i "$BACKUP_AGE_IDENTITY" -o "${workdir}/${name}" "${workdir}/${name}.age"
gzip -t "${workdir}/${name}"
local_sha="$(shasum -a 256 "${workdir}/${name}" | cut -d' ' -f1)"
echo "Decrypted ${name}, sha256 ${local_sha}"

if [ -n "$PROD_SSH" ]; then
  # shellcheck disable=SC2029
  server_sha="$(ssh "$PROD_SSH" "sha256sum '${PROD_APP_DIR}/backups/${name}' 2>/dev/null | cut -d' ' -f1" || true)"
  if [ -z "$server_sha" ]; then
    echo "Server copy of ${name} not found (expired on the server?); sha256 not compared"
  elif [ "$server_sha" = "$local_sha" ]; then
    echo "sha256 matches the server copy"
  else
    echo "sha256 differs from the server copy: ${server_sha}" >&2
    exit 1
  fi
fi

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" -e POSTGRES_USER=ainews -e POSTGRES_PASSWORD=restore-test \
  -e POSTGRES_DB=ainews "$PG_IMAGE" >/dev/null
until docker exec "$CONTAINER" pg_isready -U ainews -d ainews >/dev/null 2>&1; do sleep 1; done
# The init script restarts the server once; wait for the final start.
sleep 3
until docker exec "$CONTAINER" pg_isready -U ainews -d ainews >/dev/null 2>&1; do sleep 1; done

echo "Restoring into ${CONTAINER} (${PG_IMAGE})"
# Dump objects are owned by the prod role; --no-owner equivalent: the role is created first.
prod_role="$(gzip -cd "${workdir}/${name}" | sed -n 's/^ALTER .* OWNER TO \([a-z_][a-z0-9_]*\);$/\1/p' | head -n 1)"
if [ -n "$prod_role" ] && [ "$prod_role" != "ainews" ]; then
  docker exec "$CONTAINER" psql -q -U ainews -d ainews -c "CREATE ROLE \"${prod_role}\"" >/dev/null
fi
gzip -cd "${workdir}/${name}" | docker exec -i "$CONTAINER" psql -q -v ON_ERROR_STOP=1 -U ainews -d ainews >/dev/null

count_sql="SELECT table_name || ' ' || (xpath('/row/c/text()', query_to_xml('SELECT count(*) AS c FROM public.' || quote_ident(table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
docker exec "$CONTAINER" psql -At -U ainews -d ainews -c "$count_sql" > "${workdir}/restored_counts.txt"
echo "Row counts in the restored copy:"
cat "${workdir}/restored_counts.txt"

if [ -n "$PROD_SSH" ]; then
  # Read-only SELECT on prod; prod keeps growing after the dump, so counts may only be larger there.
  # shellcheck disable=SC2029
  ssh "$PROD_SSH" "docker exec -i ai-news-db sh -c 'psql -At -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"'" \
    <<< "$count_sql" > "${workdir}/prod_counts.txt"
  echo "Restored vs prod now (table restored prod):"
  LC_ALL=C sort -o "${workdir}/restored_counts.txt" "${workdir}/restored_counts.txt"
  LC_ALL=C sort -o "${workdir}/prod_counts.txt" "${workdir}/prod_counts.txt"
  LC_ALL=C join "${workdir}/restored_counts.txt" "${workdir}/prod_counts.txt" -a 1 -a 2 -e missing -o 0,1.2,2.2 \
    | awk '{flag = ($2 == "missing" || $3 == "missing" || $2 + 0 > $3 + 0) ? "  <-- check" : ""; print $0 flag}'
fi

echo "Restore test passed: ${object}"
