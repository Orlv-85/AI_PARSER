#!/usr/bin/env sh
# Nightly world news collect (spec 018, item 5): own timer, shared host lock, always exit 0 so a
# failure never changes another job. Off unless AINEWS_WORLD_COLLECT_ENABLED is true (about
# 820 MB of download a day). Behavior: src/app/core/world/world.md.
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"
# The switch comes from the environment, else from the deploy .env (compose reads the same file).
# Accepted in .env: "export " prefix, CRLF, quotes, trailing spaces and "# comment"; last one wins.
CR="$(printf '\r')"
TAB="$(printf '\t')"
trim() {
  v="$1"
  while :; do
    case "$v" in
      " "*|"$TAB"*) v="${v#?}";;
      *" "|*"$TAB") v="${v%?}";;
      *) break;;
    esac
  done
}
enabled="${AINEWS_WORLD_COLLECT_ENABLED:-}"
if [ -z "$enabled" ] && [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%"$CR"}"
    case "$line" in "export "*) line="${line#export }";; esac
    case "$line" in
      AINEWS_WORLD_COLLECT_ENABLED=*)
        trim "${line#*=}"
        case "$v" in *" #"*) trim "${v%% #*}";; esac
        enabled="$v"
        ;;
    esac
  done < .env
fi
trim "$enabled"
case "$v" in
  \"*\") v="${v#\"}"; v="${v%\"}";;
  \'*\') v="${v#\'}"; v="${v%\'}";;
esac
case "$v" in
  [Tt][Rr][Uu][Ee]|1|[Yy][Ee][Ss]|[Oo][Nn]) ;;
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
