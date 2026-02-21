#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

WEB_HOST_VALUE="${WEB_HOST:-127.0.0.1}"
WEB_PORT_VALUE="${WEB_PORT:-8010}"
WEB_RELOAD_VALUE="${WEB_RELOAD:-1}"
PYTHON_BIN_VALUE="${PYTHON_BIN:-}"

if [ -z "${PYTHON_BIN_VALUE}" ]; then
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
    PYTHON_BIN_VALUE="${VIRTUAL_ENV}/bin/python"
  elif [ -x "${ROOT_DIR}/venv1/bin/python" ]; then
    PYTHON_BIN_VALUE="${ROOT_DIR}/venv1/bin/python"
  elif [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    PYTHON_BIN_VALUE="${ROOT_DIR}/.venv/bin/python"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN_VALUE="python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN_VALUE="python3"
  else
    echo "Python interpreter not found. Set PYTHON_BIN or configure PATH/VIRTUAL_ENV." >&2
    exit 127
  fi
fi

if [ "${WEB_RELOAD_VALUE}" = "1" ]; then
  RELOAD_FLAG="--reload"
else
  RELOAD_FLAG=""
fi

echo "Starting web server on http://${WEB_HOST_VALUE}:${WEB_PORT_VALUE}"
PYTHONPATH=src "${PYTHON_BIN_VALUE}" -m uvicorn app.web.app:app --host "${WEB_HOST_VALUE}" --port "${WEB_PORT_VALUE}" ${RELOAD_FLAG}
