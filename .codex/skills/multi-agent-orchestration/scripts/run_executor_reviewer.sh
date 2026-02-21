#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  run_executor_reviewer.sh -C /ABS/PATH/TO/REPO -e "EXECUTOR_TASK" -r "REVIEWER_TASK" [--sandbox workspace-write]

Description:
  Runs nested Codex executor and reviewer sequentially.

Options:
  -C, --repo       Absolute path to repository
  -e, --executor   Executor task prompt
  -r, --reviewer   Reviewer task prompt
  --sandbox        Codex sandbox mode (default: workspace-write)
  -h, --help       Show this help
USAGE
}

repo=""
executor_task=""
reviewer_task=""
sandbox="workspace-write"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -C|--repo)
      repo="${2:-}"
      shift 2
      ;;
    -e|--executor)
      executor_task="${2:-}"
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

if [[ -z "$repo" || -z "$executor_task" || -z "$reviewer_task" ]]; then
  echo "Error: --repo, --executor and --reviewer are required." >&2
  usage >&2
  exit 1
fi

if [[ ! -d "$repo" ]]; then
  echo "Error: repo path does not exist: $repo" >&2
  exit 1
fi

echo "[1/2] Running executor..."
/bin/zsh -lc "codex exec -C '$repo' --sandbox '$sandbox' \"$executor_task\""

echo "[2/2] Running reviewer..."
/bin/zsh -lc "codex exec -C '$repo' --sandbox '$sandbox' \"$reviewer_task\""

audit_path="$repo/tmp/agent_audit.txt"
if [[ -f "$audit_path" ]]; then
  echo "\nReviewer audit:"
  cat "$audit_path"
else
  echo "\nReviewer finished. Audit file not found at: $audit_path"
fi

echo "\nNext: run independent checks (e.g. pytest, make lint, git diff)."
