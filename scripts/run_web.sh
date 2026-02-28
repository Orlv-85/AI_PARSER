#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

WEB_HOST_VALUE="${WEB_HOST:-127.0.0.1}"
WEB_PORT_VALUE="${WEB_PORT:-8010}"
WEB_RELOAD_VALUE="${WEB_RELOAD:-1}"
PYTHON_BIN_VALUE="${PYTHON_BIN:-}"
WEB_DB_VALUE="${WEB_DB:-postgres}"
WEB_DB_BOOTSTRAP_VALUE="${WEB_DB_BOOTSTRAP:-1}"
POSTGRES_COMPOSE_FILE_VALUE="${POSTGRES_COMPOSE_FILE:-docker-compose.local-postgres.yml}"
POSTGRES_DB_VALUE="${POSTGRES_DB:-ainews}"
POSTGRES_USER_VALUE="${POSTGRES_USER:-ainews}"
POSTGRES_PASSWORD_VALUE="${POSTGRES_PASSWORD:-change_me}"

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

if [ -z "${AINEWS_SOURCES_PATH:-}" ]; then
  AINEWS_SOURCES_PATH="${ROOT_DIR}/sources.yaml"
  export AINEWS_SOURCES_PATH
fi

if [ -z "${AINEWS_DATABASE_URL:-}" ]; then
  if [ "${WEB_DB_VALUE}" = "sqlite" ]; then
    AINEWS_DATABASE_URL="sqlite:///./data/ai_news.db"
    export AINEWS_DATABASE_URL
  elif [ "${WEB_DB_VALUE}" = "postgres" ]; then
    if [ "${WEB_DB_BOOTSTRAP_VALUE}" = "1" ]; then
      if ! command -v docker >/dev/null 2>&1; then
        echo "docker is required for WEB_DB=postgres" >&2
        exit 127
      fi
      echo "Ensuring local PostgreSQL is running via ${POSTGRES_COMPOSE_FILE_VALUE}"
      docker compose -f "${POSTGRES_COMPOSE_FILE_VALUE}" up -d db >/dev/null
      READY=0
      ATTEMPT=0
      while [ "${ATTEMPT}" -lt 30 ]; do
        if docker compose -f "${POSTGRES_COMPOSE_FILE_VALUE}" exec -T db sh -lc "pg_isready -U '${POSTGRES_USER_VALUE}' -d '${POSTGRES_DB_VALUE}'" >/dev/null 2>&1; then
          READY=1
          break
        fi
        ATTEMPT=$((ATTEMPT + 1))
        sleep 1
      done
      if [ "${READY}" -ne 1 ]; then
        echo "PostgreSQL did not become ready in time." >&2
        exit 1
      fi
    fi
    AINEWS_DATABASE_URL="postgresql+psycopg://${POSTGRES_USER_VALUE}:${POSTGRES_PASSWORD_VALUE}@127.0.0.1:5432/${POSTGRES_DB_VALUE}"
    export AINEWS_DATABASE_URL
  else
    echo "Unsupported WEB_DB value: ${WEB_DB_VALUE}. Use 'postgres' or 'sqlite'." >&2
    exit 2
  fi
fi

echo "Starting web server on http://${WEB_HOST_VALUE}:${WEB_PORT_VALUE}"
echo "Database: ${AINEWS_DATABASE_URL}"
PYTHONPATH=src "${PYTHON_BIN_VALUE}" -m uvicorn app.web.app:app --host "${WEB_HOST_VALUE}" --port "${WEB_PORT_VALUE}" ${RELOAD_FLAG}
