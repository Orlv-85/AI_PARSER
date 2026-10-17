#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
COVERAGE_FAIL_UNDER="${AINEWS_COVERAGE_FAIL_UNDER:-100}"
PYTEST_WORKERS="${AINEWS_PYTEST_WORKERS:-2}"

echo "Running tests with coverage using: ${PYTHON_BIN}"
echo "Coverage fail-under threshold: ${COVERAGE_FAIL_UNDER}%"
echo "pytest-xdist workers: ${PYTEST_WORKERS}"
"${PYTHON_BIN}" -m coverage erase
# pytest-cov measures xdist workers; plain `coverage run` would only see the controller.
"${PYTHON_BIN}" -m pytest -q -n "${PYTEST_WORKERS}" --cov --cov-report=
"${PYTHON_BIN}" -m coverage report -m --fail-under="${COVERAGE_FAIL_UNDER}"
