#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
COVERAGE_FAIL_UNDER="${AINEWS_COVERAGE_FAIL_UNDER:-100}"

echo "Running tests with coverage using: ${PYTHON_BIN}"
echo "Coverage fail-under threshold: ${COVERAGE_FAIL_UNDER}%"
"${PYTHON_BIN}" -m coverage erase
"${PYTHON_BIN}" -m coverage run -m pytest -q
"${PYTHON_BIN}" -m coverage report -m --fail-under="${COVERAGE_FAIL_UNDER}"
