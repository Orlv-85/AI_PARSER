#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
RETENTION_DAYS="${RETENTION_DAYS:-100}"
DEPLOY_TAG="${1:-}"

if [ -n "$DEPLOY_TAG" ]; then
  echo "Checking out tag: $DEPLOY_TAG"
  git fetch --tags origin
  git checkout --force "$DEPLOY_TAG"
fi

mkdir -p data backups

echo "Starting PostgreSQL..."
docker compose -f "$COMPOSE_FILE" up -d db

echo "Waiting for PostgreSQL readiness..."
attempt=0
until docker compose -f "$COMPOSE_FILE" exec -T db sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "PostgreSQL did not become ready in time" >&2
    exit 1
  fi
  sleep 2
done

echo "Building and starting app..."
docker compose -f "$COMPOSE_FILE" up -d --build app

echo "Running migrations..."
docker compose -f "$COMPOSE_FILE" run --rm app alembic upgrade head

echo "Applying retention policy..."
docker compose -f "$COMPOSE_FILE" run --rm app ai-news prune --older-than-days "$RETENTION_DAYS"

echo "Restarting app..."
docker compose -f "$COMPOSE_FILE" up -d app

echo "Checking app health..."
attempt=0
until docker compose -f "$COMPOSE_FILE" exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3)" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "App healthcheck failed" >&2
    exit 1
  fi
  sleep 2
done

echo "Deployment completed successfully."
