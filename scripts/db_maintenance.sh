#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
RETENTION_DAYS="${RETENTION_DAYS:-100}"

echo "Applying retention policy for news older than ${RETENTION_DAYS} days..."
docker compose -f "$COMPOSE_FILE" run --rm app ai-news prune --older-than-days "$RETENTION_DAYS"

echo "Running VACUUM ANALYZE on articles..."
docker compose -f "$COMPOSE_FILE" exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "VACUUM (ANALYZE) articles;"'

echo "DB maintenance completed."
