#!/usr/bin/env sh
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"
# Prefer the installed release receipt to a stale APP_IMAGE in .env.
if [ -f .last_deploy_image ]; then
  APP_IMAGE="$(cat .last_deploy_image)"
fi
export APP_IMAGE
if [ "$#" -gt 0 ]; then
  exec flock -w 7200 /tmp/ai-news-auto-update.lock docker compose \
    -f "${COMPOSE_FILE:-docker-compose.prod.yml}" run --rm app \
    ai-news daily-publish --report-date "$1"
fi
exec flock -w 7200 /tmp/ai-news-auto-update.lock docker compose \
  -f "${COMPOSE_FILE:-docker-compose.prod.yml}" run --rm app ai-news daily-publish
