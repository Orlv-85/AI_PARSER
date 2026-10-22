#!/usr/bin/env sh
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"
if [ -f .last_deploy_image ]; then
  APP_IMAGE="$(cat .last_deploy_image)"
fi
export APP_IMAGE
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
DAILY_CATCH_UP_DAYS=3
day_ago() { date -u -d "$1 days ago" +%F 2>/dev/null || date -u -v-"$1"d +%F; }

fetch_status=0
if flock -w 7200 /tmp/ai-news-auto-update.lock docker compose \
  -f "$COMPOSE_FILE" run --rm \
  -e AINEWS_CONCURRENCY_LIMIT="${AUTO_UPDATE_CONCURRENCY_LIMIT:-10}" \
  -e AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT="${AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT:-4}" \
  -e AINEWS_RSS_EXTRACT_FULL_TEXT=1 app ai-news fetch --once; then
  :
else
  fetch_status=$?
fi

if [ "$fetch_status" -eq 0 ]; then
  held_report=0
  offset=1
  while [ "$offset" -le "$DAILY_CATCH_UP_DAYS" ]; do
    day="$(day_ago "$offset")"
    report="data/daily-enrichment/$day/report.json"
    if [ -f "$report" ] && grep -q '"state": "held_collection_paused"' "$report"; then
      held_report=1
      break
    fi
    offset=$((offset + 1))
  done
  if [ "$held_report" -eq 1 ]; then
    sh "$SCRIPT_DIR/run_daily_digest_job.sh" --catch-up || true
  fi
fi

exit "$fetch_status"
