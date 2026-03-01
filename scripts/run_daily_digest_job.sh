#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

APP_CONTAINER="${AINEWS_APP_CONTAINER:-ai-news-app}"
APP_PORT="${AINEWS_DIGEST_APP_PORT:-8010}"
DIGEST_LIMIT="${AINEWS_DIGEST_LIMIT:-200}"
REPORT_DATE="${1:-$(date -u -d 'yesterday' +%F)}"

if [ -n "${AINEWS_DIGEST_APP_BASE_URL:-}" ]; then
  APP_BASE_URL="$AINEWS_DIGEST_APP_BASE_URL"
else
  APP_IP="$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$APP_CONTAINER")"
  if [ -z "$APP_IP" ]; then
    echo "Could not resolve IP for container: $APP_CONTAINER" >&2
    exit 1
  fi
  APP_BASE_URL="http://${APP_IP}:${APP_PORT}"
fi

exec python3 "$ROOT_DIR/scripts/pocketpaw_digest_bridge.py" \
  publish-feed-digest \
  --base-url "$APP_BASE_URL" \
  --report-date "$REPORT_DATE" \
  --limit "$DIGEST_LIMIT"
