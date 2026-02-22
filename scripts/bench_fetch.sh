#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.local-postgres.yml}"
LIMITS="${LIMITS:-1 5 10 20}"
RUNS_PER_LIMIT="${RUNS_PER_LIMIT:-1}"
BUILD_APP="${BUILD_APP:-0}"
ENSURE_STACK_UP="${ENSURE_STACK_UP:-1}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

now_ms() {
  python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
}

wait_for_health() {
  local url="${1:-http://127.0.0.1:8010/health}"
  local timeout_seconds="${2:-60}"
  local started
  started="$(now_ms)"

  while true; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    local current
    current="$(now_ms)"
    if (( current - started > timeout_seconds * 1000 )); then
      echo "Timed out waiting for app health at $url" >&2
      return 1
    fi
    sleep 1
  done
}

run_fetch_once() {
  local limit="$1"
  local tmp_log
  tmp_log="$(mktemp)"
  local -a run_env_args=()

  # Forward selected runtime overrides into the one-off benchmark container.
  local key
  for key in \
    AINEWS_REQUEST_TIMEOUT_SECONDS \
    AINEWS_MAX_RETRIES \
    AINEWS_PER_SOURCE_MIN_INTERVAL_SECONDS \
    AINEWS_RSS_EXTRACT_FULL_TEXT \
    AINEWS_RSS_FULL_TEXT_MAX_ITEMS_PER_SOURCE \
    AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT
  do
    if [[ -n "${!key:-}" ]]; then
      run_env_args+=(-e "${key}=${!key}")
    fi
  done

  local start_ms end_ms elapsed_ms
  start_ms="$(now_ms)"

  local -a cmd=(
    docker compose -f "$COMPOSE_FILE" run --rm
  )
  if ((${#run_env_args[@]} > 0)); then
    cmd+=("${run_env_args[@]}")
  fi
  cmd+=(
    -e "AINEWS_CONCURRENCY_LIMIT=$limit"
    ai-news ai-news fetch --once
  )

  if ! "${cmd[@]}" >"$tmp_log" 2>&1; then
    echo "FAIL (concurrency=$limit)" >&2
    cat "$tmp_log" >&2
    rm -f "$tmp_log"
    return 1
  fi

  end_ms="$(now_ms)"
  elapsed_ms=$((end_ms - start_ms))

  local summary
  summary="$(grep -E "fetch complete:" "$tmp_log" | tail -n 1 || true)"
  printf "%s\t%s\n" "$elapsed_ms" "${summary:-fetch complete: <not found in output>}"
  rm -f "$tmp_log"
}

main() {
  need_cmd docker
  need_cmd curl
  need_cmd python3

  cd "$ROOT_DIR"

  if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "Compose file not found: $COMPOSE_FILE" >&2
    exit 1
  fi

  if [[ "$ENSURE_STACK_UP" == "1" ]]; then
    echo "Starting local Postgres + app via $COMPOSE_FILE"
    if [[ "$BUILD_APP" == "1" ]]; then
      docker compose -f "$COMPOSE_FILE" up -d --build db ai-news
    else
      docker compose -f "$COMPOSE_FILE" up -d db ai-news
    fi
    wait_for_health "http://127.0.0.1:8010/health" 90
  fi

  printf "Benchmarking fetch latency (ms)\n"
  printf "compose_file=%s runs_per_limit=%s limits=%s\n" "$COMPOSE_FILE" "$RUNS_PER_LIMIT" "$LIMITS"
  printf "limit\trun\telapsed_ms\tsummary\n"

  local limit run result elapsed_ms summary
  for limit in $LIMITS; do
    for ((run = 1; run <= RUNS_PER_LIMIT; run++)); do
      result="$(run_fetch_once "$limit")"
      elapsed_ms="${result%%$'\t'*}"
      summary="${result#*$'\t'}"
      printf "%s\t%s\t%s\t%s\n" "$limit" "$run" "$elapsed_ms" "$summary"
    done
  done
}

main "$@"
