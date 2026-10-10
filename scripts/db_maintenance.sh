#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
if [ -z "${RETENTION_DAYS:-}" ] && [ -f .env ]; then
  RETENTION_DAYS="$(sed -nE "s/^[[:space:]]*(export[[:space:]]+)?RETENTION_DAYS[[:space:]]*=[[:space:]]*['\"]?([0-9]+)['\"]?([[:space:]]*#.*)?[[:space:]]*$/\\2/p" .env | tail -n 1)"
fi
RETENTION_DAYS="${RETENTION_DAYS:-800}"
DB_MAX_SIZE_GB="${DB_MAX_SIZE_GB:-5}"
DB_TARGET_SIZE_GB="${DB_TARGET_SIZE_GB:-4}"
DB_RETENTION_STEP_DAYS="${DB_RETENTION_STEP_DAYS:-7}"

if [ "$DB_TARGET_SIZE_GB" -ge "$DB_MAX_SIZE_GB" ]; then
  echo "DB_TARGET_SIZE_GB must be lower than DB_MAX_SIZE_GB" >&2
  exit 1
fi

if [ "$DB_RETENTION_STEP_DAYS" -le 0 ]; then
  echo "DB_RETENTION_STEP_DAYS must be greater than 0" >&2
  exit 1
fi

max_bytes=$((DB_MAX_SIZE_GB * 1024 * 1024 * 1024))
target_bytes=$((DB_TARGET_SIZE_GB * 1024 * 1024 * 1024))

get_db_size_bytes() {
  docker compose -f "$COMPOSE_FILE" exec -T db sh -lc \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT pg_database_size(current_database());"' \
    | tr -d '[:space:]'
}

vacuum_analyze_articles() {
  echo "Running VACUUM ANALYZE on articles..."
  docker compose -f "$COMPOSE_FILE" exec -T db sh -lc \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "VACUUM (ANALYZE) articles;"'
}

apply_prune() {
  prune_days="$1"
  echo "Applying retention policy for news older than ${prune_days} days..."
  docker compose -f "$COMPOSE_FILE" run --rm app ai-news prune --older-than-days "$prune_days"
  vacuum_analyze_articles
}

apply_prune "$RETENTION_DAYS"

current_size="$(get_db_size_bytes)"
echo "Current DB size: ${current_size} bytes"

if [ "$current_size" -ge "$max_bytes" ]; then
  echo "DB size reached ${DB_MAX_SIZE_GB} GB threshold; tightening retention until <= ${DB_TARGET_SIZE_GB} GB."
  current_retention="$RETENTION_DAYS"
  while [ "$current_size" -gt "$target_bytes" ] && [ "$current_retention" -gt 1 ]; do
    next_retention=$((current_retention - DB_RETENTION_STEP_DAYS))
    if [ "$next_retention" -lt 1 ]; then
      next_retention=1
    fi
    if [ "$next_retention" -eq "$current_retention" ]; then
      break
    fi
    apply_prune "$next_retention"
    current_retention="$next_retention"
    current_size="$(get_db_size_bytes)"
    echo "Current DB size after prune(${current_retention}): ${current_size} bytes"
  done
fi

if [ "$current_size" -gt "$target_bytes" ]; then
  echo "Warning: DB size is still above target (${DB_TARGET_SIZE_GB} GB): ${current_size} bytes." >&2
  echo "Consider stronger cleanup policy or VACUUM FULL in maintenance window." >&2
else
  echo "DB size is within target (${DB_TARGET_SIZE_GB} GB): ${current_size} bytes."
fi

echo "DB maintenance completed."
