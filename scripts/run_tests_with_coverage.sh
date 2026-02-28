#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "Running tests with coverage using: ${PYTHON_BIN}"
"${PYTHON_BIN}" -m coverage erase
"${PYTHON_BIN}" -m coverage run -m pytest -q
"${PYTHON_BIN}" -m coverage report -m --fail-under=90
