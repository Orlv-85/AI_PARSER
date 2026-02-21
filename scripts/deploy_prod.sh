#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
RETENTION_DAYS="${RETENTION_DAYS:-100}"
DEPLOY_TAG="${1:-}"
FORCE_BUILD="${FORCE_BUILD:-0}"
PREVIOUS_COMMIT="$(git rev-parse --verify HEAD 2>/dev/null || true)"

if [ -n "$DEPLOY_TAG" ]; then
  echo "Checking out tag: $DEPLOY_TAG"
  git fetch --tags origin
  git checkout --force "$DEPLOY_TAG"
fi

CURRENT_COMMIT="$(git rev-parse --verify HEAD)"

should_build=0
build_reason=""
if [ "$FORCE_BUILD" = "1" ]; then
  should_build=1
  build_reason="FORCE_BUILD=1"
elif [ -z "$PREVIOUS_COMMIT" ] || [ "$PREVIOUS_COMMIT" = "$CURRENT_COMMIT" ]; then
  should_build=1
  build_reason="initial deploy or unknown previous commit"
else
  changed_files="$(git diff --name-only "$PREVIOUS_COMMIT" "$CURRENT_COMMIT" || true)"
  if echo "$changed_files" | grep -Eq '^(build/Dockerfile|Dockerfile|requirements[^/]*\.txt|requirements/|pyproject\.toml|poetry\.lock)'; then
    should_build=1
    build_reason="image build inputs changed"
  fi
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

if [ "$should_build" -eq 1 ]; then
  echo "Building and starting app (${build_reason})..."
  docker compose -f "$COMPOSE_FILE" up -d --build app
else
  echo "Starting app without rebuild (no build input changes detected)..."
  docker compose -f "$COMPOSE_FILE" up -d app
fi

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
