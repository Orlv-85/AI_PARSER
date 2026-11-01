#!/usr/bin/env sh
# Nightly world news job (spec 018, item 5): collect the previous UTC day, screen it with Jev, fetch
# the texts of the top stories, screen again (FR-001 questions on the new texts). Own timer, shared
# host lock, always exit 0 so a failure never changes another job. Off unless
# AINEWS_WORLD_COLLECT_ENABLED is true (about 820 MB of download a day). Behavior:
# src/app/core/world/world.md.
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"
# Settings come from the environment, else from the deploy .env (compose reads the same file).
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
# env_value NAME: the value of NAME into $v.
env_value() {
  eval "v=\"\${$1:-}\""
  if [ -z "$v" ] && [ -f .env ]; then
    found=""
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%"$CR"}"
      case "$line" in "export "*) line="${line#export }";; esac
      case "$line" in
        "$1="*)
          trim "${line#*=}"
          case "$v" in *" #"*) trim "${v%% #*}";; esac
          found="$v"
          ;;
      esac
    done < .env
    v="$found"
  fi
  trim "$v"
  case "$v" in
    \"*\") v="${v#\"}"; v="${v%\"}";;
    \'*\') v="${v#\'}"; v="${v%\'}";;
  esac
}
env_value AINEWS_WORLD_COLLECT_ENABLED
case "$v" in
  [Tt][Rr][Uu][Ee]|1|[Yy][Ee][Ss]|[Oo][Nn]) ;;
  *)
    echo "world collect skipped: AINEWS_WORLD_COLLECT_ENABLED is off" >&2
    exit 0
    ;;
esac
env_value JEV_API_KEY
HAVE_JEV=0
[ -n "$v" ] && HAVE_JEV=1
# Without the release image compose falls back to a stale local :latest.
if [ -f .last_deploy_image ]; then
  APP_IMAGE="$(cat .last_deploy_image)"
fi
export APP_IMAGE
LOCK=/tmp/ai-news-auto-update.lock
LOCK_WAIT=1800
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
NAME=ai-news-world
# Seconds per step. With the lock wait, a 30 s kill grace and a 60 s container removal for each
# step they must stay below TimeoutStartSec of ai-news-daily-world in install_daily_timers.sh.
COLLECT_LIMIT=2400  # gate run: about 4 min a day; two days on a first night, plus slow files
SCREEN_LIMIT=2700   # 1,842 title requests one at a time; a cut run leaves the rest for the next
TEXTS_LIMIT=900     # up to 100 pages, 4 at a time, 1 s apart per host
ASSESS_LIMIT=900    # step B: up to 100 requests with a page text each
yesterday() { date -u -d yesterday +%F 2>/dev/null || date -u -v-1d +%F; }
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
DAY="$(yesterday)"
# run_step LABEL SECONDS ARGS...: one container; a failure or timeout is one line, the job goes on.
run_step() {
  step="$1"
  limit="$2"
  shift 2
  # A container left by a killed run would make --name fail.
  timeout -k 10 60 docker rm -f "$NAME" >/dev/null 2>&1 || true
  timeout -k 30 "$limit" docker compose -f "$COMPOSE_FILE" run --rm --name "$NAME" app \
    ai-news "$@" \
    || {
      status=$?
      echo "world ${step} failed or timed out (exit ${status}); other jobs are unaffected" >&2
      timeout -k 10 60 docker rm -f "$NAME" >/dev/null 2>&1 || true
    }
}
# jev_step LABEL SECONDS ARGS...: a step that needs the Jev key.
jev_step() {
  if [ "$HAVE_JEV" -eq 1 ]; then
    run_step "$@"
  else
    echo "world $1 skipped: JEV_API_KEY is not set" >&2
  fi
}
# The summary is already logged on stderr; drop the CLI's stdout copy so the log has it once.
run_step collect "$COLLECT_LIMIT" world collect >/dev/null
jev_step screen "$SCREEN_LIMIT" world screen --date "$DAY"
run_step texts "$TEXTS_LIMIT" world texts --date "$DAY"
jev_step screen-b "$ASSESS_LIMIT" world screen --date "$DAY"
exit 0
