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
yesterday() { date -u -d yesterday +%F 2>/dev/null || date -u -v-1d +%F; }
if [ -z "${AINEWS_DAILY_JOB_LOCKED:-}" ]; then
  AINEWS_DAILY_JOB_START="$(date +%s)"
  REPORT_DATE="${1:-$(yesterday)}"
  AINEWS_DAILY_JOB_LOCKED=1
  export AINEWS_DAILY_JOB_START REPORT_DATE AINEWS_DAILY_JOB_LOCKED
  # One host lock for publication and signals.
  exec flock -w 7200 "$LOCK" sh "$SCRIPT_DIR/$(basename "$0")"
fi
AINEWS_DAILY_JOB_START="${AINEWS_DAILY_JOB_START:-$(date +%s)}"
REPORT_DATE="${REPORT_DATE:-$(yesterday)}"
# The digest decides the job result (set -e exits on failure).
docker compose -f "$COMPOSE_FILE" run --rm app ai-news daily-publish --report-date "$REPORT_DATE"
# Signals: start only if >= 300 s remain after reserving 600 s for shutdown and slack.
remaining=$((BUDGET - ($(date +%s) - AINEWS_DAILY_JOB_START) - 600))
if [ "$remaining" -lt 300 ]; then
  echo "daily-signals skipped: not enough time left in the job budget" >&2
  exit 0
fi
if [ "$remaining" -gt 2700 ]; then remaining=2700; fi
name="ai-news-signals-$REPORT_DATE"
limit=""
if command -v timeout >/dev/null 2>&1; then limit="timeout -k 30 $remaining"; fi
# The app stops dispatching 180 s before the outer limit to finish snapshots and exit cleanly.
# $limit is unquoted on purpose: it expands to the timeout command words or to nothing.
$limit docker compose -f "$COMPOSE_FILE" run --rm --name "$name" app ai-news daily-signals \
  --report-date "$REPORT_DATE" --max-seconds "$((remaining - 180))" \
  || {
    echo "daily-signals failed or timed out; the published digest is unaffected" >&2
    docker rm -f "$name" >/dev/null 2>&1 || true
  }
exit 0
