#!/usr/bin/env sh
# Nightly world news collect (spec 018, item 5): own timer, shared host lock, always exit 0 so a
# failure never changes another job. Off unless AINEWS_WORLD_COLLECT_ENABLED is true (about
# 820 MB of download a day). Behavior: src/app/core/world/world.md.
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"
# The switch comes from the environment, else from the deploy .env (compose reads the same file).
enabled="${AINEWS_WORLD_COLLECT_ENABLED:-}"
if [ -z "$enabled" ] && [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in AINEWS_WORLD_COLLECT_ENABLED=*) enabled="${line#*=}";; esac
  done < .env
fi
case "$enabled" in
  true|True|TRUE|1|yes|on|'"true"'|"'true'") ;;
  *)
    echo "world collect skipped: AINEWS_WORLD_COLLECT_ENABLED is off" >&2
    exit 0
    ;;
esac
# Without the release image compose falls back to a stale local :latest.
if [ -f .last_deploy_image ]; then
  APP_IMAGE="$(cat .last_deploy_image)"
fi
export APP_IMAGE
LOCK=/tmp/ai-news-auto-update.lock
LOCK_WAIT=1800
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
NAME=ai-news-world
# The locked re-exec always exits 0, so a non-zero flock status means the lock was not acquired.
if [ "${1:-}" != "--locked" ]; then
  flock -w "$LOCK_WAIT" "$LOCK" sh "$SCRIPT_DIR/$(basename "$0")" --locked \
    || echo "world collect skipped: host lock not acquired within ${LOCK_WAIT} s" >&2
  exit 0
fi
if ! command -v timeout >/dev/null 2>&1; then
  echo "world collect skipped: timeout is not installed" >&2
  exit 0
fi
# A container left by a killed run would make --name fail.
timeout -k 10 60 docker rm -f "$NAME" >/dev/null 2>&1 || true
# The summary is already logged on stderr; drop the CLI's stdout copy so the log has it once.
timeout -k 30 3300 docker compose -f "$COMPOSE_FILE" run --rm --name "$NAME" app \
  ai-news world collect >/dev/null \
  || {
    status=$?
    echo "world collect failed or timed out (exit ${status}); other jobs are unaffected" >&2
    timeout -k 10 60 docker rm -f "$NAME" >/dev/null 2>&1 || true
  }
exit 0
