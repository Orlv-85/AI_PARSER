#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

: "${AINEWS_CONCURRENCY_LIMIT:=10}"
: "${AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT:=4}"
: "${AINEWS_BIN:=ai-news}"

export AINEWS_CONCURRENCY_LIMIT
export AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] auto_update_once starting" >&2
echo "AINEWS_CONCURRENCY_LIMIT=${AINEWS_CONCURRENCY_LIMIT}" >&2
echo "AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT=${AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT}" >&2

"${AINEWS_BIN}" fetch --once
