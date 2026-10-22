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
LOCK=/tmp/ai-news-auto-update.lock
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BUDGET=14400 # must match TimeoutStartSec in install_daily_timers.sh
DAILY_CATCH_UP_DAYS=3
yesterday() { date -u -d yesterday +%F 2>/dev/null || date -u -v-1d +%F; }
day_ago() { date -u -d "$1 days ago" +%F 2>/dev/null || date -u -v-"$1"d +%F; }
# The locked re-exec passes its mode, date (when supplied) and start time as arguments.
if [ "${1:-}" != "--locked" ]; then
  if [ "${1:-}" = "--catch-up" ]; then
    exec flock -w 7200 "$LOCK" sh "$SCRIPT_DIR/$(basename "$0")" --locked \
      --catch-up "$(date +%s)"
  fi
  exec flock -w 7200 "$LOCK" sh "$SCRIPT_DIR/$(basename "$0")" --locked \
    "${1:-$(yesterday)}" "$(date +%s)"
fi
if [ "${2:-}" = "--catch-up" ]; then
  CATCH_UP=1
  REPORT_DATE=""
  AINEWS_DAILY_JOB_START="${3:-$(date +%s)}"
else
  CATCH_UP=0
  REPORT_DATE="${2:-$(yesterday)}"
  AINEWS_DAILY_JOB_START="${3:-$(date +%s)}"
fi

CATCH_UP_DATES=""
if [ "$CATCH_UP" -eq 1 ]; then
  offset=$DAILY_CATCH_UP_DAYS
  while [ "$offset" -ge 1 ]; do
    day="$(day_ago "$offset")"
    report="data/daily-enrichment/$day/report.json"
    if [ -f "$report" ] && grep -q '"state": "held_collection_paused"' "$report"; then
      CATCH_UP_DATES="$CATCH_UP_DATES $day"
    elif [ "$offset" -eq 1 ] && [ ! -f "$report" ]; then
      CATCH_UP_DATES="$CATCH_UP_DATES $day"
    fi
    offset=$((offset - 1))
  done
  if docker compose -f "$COMPOSE_FILE" run --rm app ai-news daily-publish --catch-up; then
    :
  else
    publish_status=$?
    if [ "$publish_status" -eq 2 ]; then
      echo "daily-publish held: collection paused" >&2
      exit 0
    fi
    exit "$publish_status"
  fi
else
  if docker compose -f "$COMPOSE_FILE" run --rm app ai-news daily-publish --report-date "$REPORT_DATE"; then
    :
  else
    publish_status=$?
    if [ "$publish_status" -eq 2 ]; then
      echo "daily-publish held: collection paused" >&2
      exit 0
    fi
    exit "$publish_status"
  fi
fi

if [ "$CATCH_UP" -eq 1 ]; then
  SIGNAL_DATES=""
  for day in $CATCH_UP_DATES; do
    report="data/daily-enrichment/$day/report.json"
    if [ -f "$report" ] && grep -q '"state": "published' "$report"; then
      SIGNAL_DATES="$SIGNAL_DATES $day"
    fi
  done
else
  SIGNAL_DATES="$REPORT_DATE"
fi

# Signals share the publication budget. Each date gets a bounded step from what remains.
for SIGNAL_DATE in $SIGNAL_DATES; do
  remaining=$((BUDGET - ($(date +%s) - AINEWS_DAILY_JOB_START) - 600))
  if [ "$remaining" -lt 300 ]; then
    echo "daily-signals skipped: not enough time left in the job budget" >&2
    exit 0
  fi
  if [ "$remaining" -gt 2700 ]; then remaining=2700; fi
  # Without `timeout` the step has no hard bound; skip it rather than hold the host lock.
  if ! command -v timeout >/dev/null 2>&1; then
    echo "daily-signals skipped: timeout is not installed" >&2
    exit 0
  fi
  name="ai-news-signals-$SIGNAL_DATE"
  # The app stops dispatching 180 s before the outer limit to finish snapshots and exit cleanly.
  timeout -k 30 "$remaining" docker compose -f "$COMPOSE_FILE" run --rm --name "$name" app \
    ai-news daily-signals --report-date "$SIGNAL_DATE" --max-seconds "$((remaining - 180))" \
    || {
      echo "daily-signals failed or timed out; the published digest is unaffected" >&2
      timeout -k 10 60 docker rm -f "$name" >/dev/null 2>&1 || true
    }
done
exit 0
