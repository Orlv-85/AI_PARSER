#!/usr/bin/env sh
# Daily bulletin (018 item 4b). Behavior: src/app/usecases/bulletin/daily.md.
# Off unless explicitly enabled: this command can call Jev and DeepSeek.
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"
# Same environment/.env parsing as the world job; do not source shell code from .env.
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
env_value AINEWS_BULLETIN_JOB_ENABLED
case "$v" in
  [Tt][Rr][Uu][Ee]|1|[Yy][Ee][Ss]|[Oo][Nn]) ;;
  *)
    echo "bulletin daily skipped: AINEWS_BULLETIN_JOB_ENABLED is off" >&2
    exit 0
    ;;
esac
if [ -f .last_deploy_image ]; then
  APP_IMAGE="$(cat .last_deploy_image)"
fi
export APP_IMAGE
LOCK=/tmp/ai-news-auto-update.lock
LOCK_WAIT=8100
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
NAME=ai-news-bulletin
# One CLI step includes assessment, build and writer; service also covers cleanup and kill grace.
DAILY_LIMIT=1800
if [ "${1:-}" != "--locked" ]; then
  flock -w "$LOCK_WAIT" "$LOCK" sh "$SCRIPT_DIR/$(basename "$0")" --locked \
    || echo "bulletin daily skipped: host lock not acquired within ${LOCK_WAIT} s" >&2
  exit 0
fi
if ! command -v timeout >/dev/null 2>&1; then
  echo "bulletin daily skipped: timeout is not installed" >&2
  exit 0
fi
run_step() {
  step="$1"
  limit="$2"
  shift 2
  timeout -k 10 60 docker rm -f "$NAME" >/dev/null 2>&1 || true
  timeout -k 30 "$limit" docker compose -f "$COMPOSE_FILE" run --rm --name "$NAME" app \
    ai-news "$@" \
    || {
      status=$?
      echo "bulletin ${step} failed or timed out (exit ${status}); other jobs are unaffected" >&2
      timeout -k 10 60 docker rm -f "$NAME" >/dev/null 2>&1 || true
    }
}
run_step daily "$DAILY_LIMIT" bulletin daily
exit 0
