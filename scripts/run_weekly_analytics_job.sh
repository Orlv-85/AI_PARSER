#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

APP_CONTAINER="${AINEWS_APP_CONTAINER:-ai-news-app}"
APP_PORT="${AINEWS_DIGEST_APP_PORT:-8010}"
WEEKLY_LIMIT="${AINEWS_WEEKLY_LIMIT:-200}"

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

if [ "$#" -ge 1 ]; then
  REPORT_DATE="$1"
else
  REPORT_DATE="$(python3 - <<'PY'
from datetime import UTC, datetime, timedelta

today = datetime.now(UTC).date()
# Most recent Sunday (Mon->yesterday; Tue..Sun->latest Sunday)
days_back = (today.weekday() - 6) % 7
print((today - timedelta(days=days_back)).isoformat())
PY
)"
fi

exec python3 "$ROOT_DIR/scripts/pocketpaw_digest_bridge.py" \
  publish-feed-weekly \
  --base-url "$APP_BASE_URL" \
  --report-date "$REPORT_DATE" \
  --limit "$WEEKLY_LIMIT"
