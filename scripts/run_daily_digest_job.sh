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
# The locked re-exec passes its marker, date and start time as arguments; nothing is taken
# from the inherited environment.
if [ "${1:-}" != "--locked" ]; then
  # One host lock for publication and signals.
  exec flock -w 7200 "$LOCK" sh "$SCRIPT_DIR/$(basename "$0")" --locked \
    "${1:-$(yesterday)}" "$(date +%s)"
fi
REPORT_DATE="${2:-$(yesterday)}"
AINEWS_DAILY_JOB_START="${3:-$(date +%s)}"
# The digest decides the job result (set -e exits on failure).
docker compose -f "$COMPOSE_FILE" run --rm app ai-news daily-publish --report-date "$REPORT_DATE"
# Signals: start only if >= 300 s remain after reserving 600 s for shutdown and slack.
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
name="ai-news-signals-$REPORT_DATE"
# The app stops dispatching 180 s before the outer limit to finish snapshots and exit cleanly.
timeout -k 30 "$remaining" docker compose -f "$COMPOSE_FILE" run --rm --name "$name" app \
  ai-news daily-signals --report-date "$REPORT_DATE" --max-seconds "$((remaining - 180))" \
  || {
    echo "daily-signals failed or timed out; the published digest is unaffected" >&2
    timeout -k 10 60 docker rm -f "$name" >/dev/null 2>&1 || true
  }
exit 0
