#!/usr/bin/env sh
# Prints "<table> <row count>" for every public table, sorted, from the running db container.
# Read-only. Used to compare the database before and after moving it (docs/archive/2026-10/db-volume-move.md).
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

docker compose -f "$COMPOSE_FILE" exec -T db sh -lc 'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL' | LC_ALL=C sort
SELECT table_name || ' ' || (xpath('/row/c/text()',
  query_to_xml('SELECT count(*) AS c FROM public.' || quote_ident(table_name), false, true, '')))[1]::text
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;
SQL
