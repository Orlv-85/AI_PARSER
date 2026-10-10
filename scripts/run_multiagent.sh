#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
local_runner="$repo_root/scripts/run_executor_reviewer.sh"
skill_runner="$repo_root/.codex/skills/multi-agent-orchestration/scripts/run_executor_reviewer.sh"

if [[ -x "$local_runner" ]]; then
  exec "$local_runner" "$@"
fi

exec "$skill_runner" "$@"
