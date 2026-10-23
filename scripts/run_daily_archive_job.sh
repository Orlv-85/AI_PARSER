#!/usr/bin/env sh
# Nightly archive capture (spec 016): own timer, shared host lock, always exit 0 so a failure
# never changes another job. Behavior: src/app/core/archive/capture.md.
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"
# Without the release image compose falls back to a stale local :latest.
if [ -f .last_deploy_image ]; then
  APP_IMAGE="$(cat .last_deploy_image)"
fi
export APP_IMAGE
LOCK=/tmp/ai-news-auto-update.lock
LOCK_WAIT=1800
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
NAME=ai-news-archive
# The locked re-exec always exits 0, so a non-zero flock status means the lock was not acquired.
if [ "${1:-}" != "--locked" ]; then
  flock -w "$LOCK_WAIT" "$LOCK" sh "$SCRIPT_DIR/$(basename "$0")" --locked \
    || echo "archive capture skipped: host lock not acquired within ${LOCK_WAIT} s" >&2
  exit 0
fi
if ! command -v timeout >/dev/null 2>&1; then
  echo "archive capture skipped: timeout is not installed" >&2
  exit 0
fi
# A container left by a killed run would make --name fail.
timeout -k 10 60 docker rm -f "$NAME" >/dev/null 2>&1 || true
timeout -k 30 1680 docker compose -f "$COMPOSE_FILE" run --rm --name "$NAME" app \
  ai-news archive capture --max-seconds 1500 \
  || {
    status=$?
    echo "archive capture failed or timed out (exit ${status}); other jobs are unaffected" >&2
    timeout -k 10 60 docker rm -f "$NAME" >/dev/null 2>&1 || true
  }
exit 0
