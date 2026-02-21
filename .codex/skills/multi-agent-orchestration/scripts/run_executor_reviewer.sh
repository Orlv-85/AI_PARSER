#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  run_executor_reviewer.sh -C /ABS/PATH/TO/REPO -t "TESTER_TASK" -g "GENERATOR_TASK" -r "REVIEWER_TASK" [options]
  run_executor_reviewer.sh -C /ABS/PATH/TO/REPO -e "EXECUTOR_TASK" -r "REVIEWER_TASK" [options]

Description:
  Runs nested Codex agents sequentially with retries and stable shell defaults.
  Primary pattern: tester -> generator -> reviewer.
  Legacy mode: executor -> reviewer (using -e and -r).

Options:
  -C, --repo            Absolute path to repository
  -t, --tester          Tester task prompt
  -g, --generator       Generator task prompt
  -r, --reviewer        Reviewer task prompt
  -e, --executor        Legacy alias for generator prompt
  --sandbox             Codex sandbox mode (default: workspace-write)
  --retries N           Retry attempts per agent (default: 3)
  --backoff SEC_LIST    Comma-separated backoff seconds (default: 5,10,20)
  --tag NAME            Prefix for tmp artifacts (default: multiagent)
  --tester-handoff P    Expected tester handoff file (default: tmp/tester_out.md)
  --generator-handoff P Expected generator handoff file (default: tmp/generator_out.md)
  --reviewer-handoff P  Expected reviewer handoff file (default: tmp/reviewer_out.md)
  -h, --help            Show this help
USAGE
}

repo=""
tester_task=""
generator_task=""
reviewer_task=""
sandbox="workspace-write"
retries=3
backoff_csv="5,10,20"
tag="multiagent"
tester_handoff="tmp/tester_out.md"
generator_handoff="tmp/generator_out.md"
reviewer_handoff="tmp/reviewer_out.md"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -C|--repo)
      repo="${2:-}"
      shift 2
      ;;
    -t|--tester)
      tester_task="${2:-}"
      shift 2
      ;;
    -g|--generator)
      generator_task="${2:-}"
      shift 2
      ;;
    -e|--executor)
      generator_task="${2:-}"
      shift 2
      ;;
    -r|--reviewer)
      reviewer_task="${2:-}"
      shift 2
      ;;
    --sandbox)
      sandbox="${2:-}"
      shift 2
      ;;
    --retries)
      retries="${2:-}"
      shift 2
      ;;
    --backoff)
      backoff_csv="${2:-}"
      shift 2
      ;;
    --tag)
      tag="${2:-}"
      shift 2
      ;;
    --tester-handoff)
      tester_handoff="${2:-}"
      shift 2
      ;;
    --generator-handoff)
      generator_handoff="${2:-}"
      shift 2
      ;;
    --reviewer-handoff)
      reviewer_handoff="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$repo" || -z "$reviewer_task" ]]; then
  echo "Error: --repo and --reviewer are required." >&2
  usage >&2
  exit 1
fi

if [[ -z "$tester_task" && -z "$generator_task" ]]; then
  echo "Error: provide either tester+generator (-t and -g) or legacy executor (-e)." >&2
  usage >&2
  exit 1
fi

if [[ ! -d "$repo" ]]; then
  echo "Error: repo path does not exist: $repo" >&2
  exit 1
fi

if ! [[ "$retries" =~ ^[0-9]+$ ]] || [[ "$retries" -lt 1 ]]; then
  echo "Error: --retries must be an integer >= 1" >&2
  exit 1
fi

mkdir -p "$repo/tmp"

IFS=',' read -r -a backoff_values <<< "$backoff_csv"

run_agent() {
  local role="$1"
  local prompt="$2"
  local handoff_rel="$3"
  local message_rel="tmp/${tag}_${role}_last.md"
  local prompt_abs="$repo/tmp/${tag}_${role}_prompt.txt"
  local handoff_abs="$repo/$handoff_rel"
  local message_abs="$repo/$message_rel"
  local log_abs="$repo/tmp/${tag}_${role}.log"

  printf "%s\n" "$prompt" > "$prompt_abs"

  local attempt=1
  while [[ "$attempt" -le "$retries" ]]; do
    echo "[${role}] attempt ${attempt}/${retries}"
    set +e
    /bin/zsh -f -lc "codex exec -C '$repo' --sandbox '$sandbox' --output-last-message '$message_rel' \"\$(cat '$prompt_abs')\"" \
      >"$log_abs" 2>&1
    local rc=$?
    set -e

    if [[ "$rc" -eq 0 ]]; then
      echo "[${role}] exit code 0"
      return 0
    fi

    # Nested codex may still produce artifacts despite transport errors.
    if [[ -s "$handoff_abs" || -s "$message_abs" ]]; then
      echo "[${role}] non-zero exit but artifact exists; continuing."
      return 0
    fi

    if [[ "$attempt" -lt "$retries" ]]; then
      local idx=$((attempt - 1))
      local sleep_sec=5
      if [[ "$idx" -lt "${#backoff_values[@]}" && -n "${backoff_values[$idx]}" ]]; then
        sleep_sec="${backoff_values[$idx]}"
      fi
      echo "[${role}] retrying in ${sleep_sec}s"
      sleep "$sleep_sec"
    fi
    attempt=$((attempt + 1))
  done

  echo "[${role}] failed after ${retries} attempts. Log: $log_abs" >&2
  return 1
}

if [[ -n "$tester_task" ]]; then
  echo "[1/3] Running tester..."
  run_agent "tester" "$tester_task" "$tester_handoff"
else
  echo "[1/2] Tester step skipped (legacy mode)."
fi

echo "[2/3] Running generator/executor..."
run_agent "generator" "$generator_task" "$generator_handoff"

echo "[3/3] Running reviewer..."
run_agent "reviewer" "$reviewer_task" "$reviewer_handoff"

echo ""
if [[ -f "$repo/$reviewer_handoff" ]]; then
  echo "Reviewer handoff ($reviewer_handoff):"
  cat "$repo/$reviewer_handoff"
else
  echo "Reviewer finished. Handoff file not found at: $repo/$reviewer_handoff"
fi

echo ""
echo "Next: run independent checks (e.g. pytest, make lint, git diff)."
