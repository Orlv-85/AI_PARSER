#!/usr/bin/env sh
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"
if [ -f .last_deploy_image ]; then
  APP_IMAGE="$(cat .last_deploy_image)"
fi
export APP_IMAGE
exec flock -w 7200 /tmp/ai-news-auto-update.lock docker compose \
  -f "${COMPOSE_FILE:-docker-compose.prod.yml}" run --rm \
  -e AINEWS_CONCURRENCY_LIMIT="${AUTO_UPDATE_CONCURRENCY_LIMIT:-10}" \
  -e AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT="${AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT:-4}" \
  -e AINEWS_RSS_EXTRACT_FULL_TEXT=1 app ai-news fetch --once
