#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$repo_root/.codex/skills/multi-agent-orchestration/scripts/run_executor_reviewer.sh" "$@"
