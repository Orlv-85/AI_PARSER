#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

APP_CONTAINER="${AINEWS_APP_CONTAINER:-ai-news-app}"
APP_BASE_URL="${AINEWS_DIGEST_APP_BASE_URL:-http://127.0.0.1:8010}"
DIGEST_LIMIT="${AINEWS_DIGEST_LIMIT:-200}"
REPORT_DATE="${1:-$(date -u -d 'yesterday' +%F)}"

exec docker exec "$APP_CONTAINER" python /app/scripts/pocketpaw_digest_bridge.py \
  publish-feed-digest \
  --base-url "$APP_BASE_URL" \
  --report-date "$REPORT_DATE" \
  --limit "$DIGEST_LIMIT"
