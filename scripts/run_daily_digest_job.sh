#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

APP_CONTAINER="${AINEWS_APP_CONTAINER:-ai-news-app}"
APP_PORT="${AINEWS_DIGEST_APP_PORT:-8010}"
DIGEST_LIMIT="${AINEWS_DIGEST_LIMIT:-200}"
DEEPSEEK_MODEL="${AINEWS_DIGEST_MODEL:-}"
ALLOW_FALLBACK="${AINEWS_DIGEST_ALLOW_FALLBACK:-1}"
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

if [ -z "${DS_API_KEY:-}" ] && [ -f "$ROOT_DIR/.env" ]; then
  DS_API_KEY="$(sed -n 's/^DS_API_KEY=//p' "$ROOT_DIR/.env" | tail -n 1)"
fi
if [ -z "$DEEPSEEK_MODEL" ] && [ -f "$ROOT_DIR/.env" ]; then
  DEEPSEEK_MODEL="$(sed -n 's/^AINEWS_DIGEST_MODEL=//p' "$ROOT_DIR/.env" | tail -n 1)"
fi
DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-flash}"
export DS_API_KEY

if python3 "$ROOT_DIR/scripts/pocketpaw_digest_bridge.py" \
  publish-deepseek-digest \
  --base-url "$APP_BASE_URL" \
  --report-date "$REPORT_DATE" \
  --limit "$DIGEST_LIMIT" \
  --model "$DEEPSEEK_MODEL"; then
  exit 0
fi
if [ "$ALLOW_FALLBACK" != "1" ]; then
  exit 1
fi

echo "DeepSeek unavailable; using source text excerpts (not AI summaries)" >&2
exec python3 "$ROOT_DIR/scripts/pocketpaw_digest_bridge.py" \
  publish-feed-digest \
  --base-url "$APP_BASE_URL" \
  --report-date "$REPORT_DATE" \
  --limit "$DIGEST_LIMIT"
