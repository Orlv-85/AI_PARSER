#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="${BACKUP_DIR}/postgres_${timestamp}.sql.gz"

echo "Creating backup: ${backup_file}"
docker compose -f "$COMPOSE_FILE" exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > "$backup_file"

echo "Cleaning old backups (> ${BACKUP_RETENTION_DAYS} days)..."
find "$BACKUP_DIR" -type f -name "postgres_*.sql.gz" -mtime +"$BACKUP_RETENTION_DAYS" -delete

echo "Backup completed."
