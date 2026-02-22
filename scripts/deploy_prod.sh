#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
RETENTION_DAYS="${RETENTION_DAYS:-100}"
DEPLOY_TAG="${1:-}"
FORCE_BUILD="${FORCE_BUILD:-0}"
LAST_DEPLOY_FILE="${LAST_DEPLOY_FILE:-.last_deploy_commit}"
AUTO_UPDATE_ENABLED="${AUTO_UPDATE_ENABLED:-1}"
AUTO_UPDATE_CRON_SCHEDULE="${AUTO_UPDATE_CRON_SCHEDULE:-*/30 * * * *}"
AUTO_UPDATE_LOG_PATH="${AUTO_UPDATE_LOG_PATH:-/var/log/ai-news-auto-update.log}"
AUTO_UPDATE_CONCURRENCY_LIMIT="${AUTO_UPDATE_CONCURRENCY_LIMIT:-20}"
AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT="${AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT:-8}"

if [ -n "$DEPLOY_TAG" ]; then
  echo "Checking out tag: $DEPLOY_TAG"
  git fetch --tags origin
  git checkout --force "$DEPLOY_TAG"
fi

CURRENT_COMMIT="$(git rev-parse --verify HEAD)"
LAST_DEPLOY_COMMIT=""
if [ -f "$LAST_DEPLOY_FILE" ]; then
  LAST_DEPLOY_COMMIT="$(head -n 1 "$LAST_DEPLOY_FILE" | tr -d '[:space:]')"
fi

should_build=0
build_reason=""
if [ "$FORCE_BUILD" = "1" ]; then
  should_build=1
  build_reason="FORCE_BUILD=1"
elif [ -z "$LAST_DEPLOY_COMMIT" ]; then
  should_build=1
  build_reason="initial deploy (no last deploy marker)"
elif [ "$LAST_DEPLOY_COMMIT" = "$CURRENT_COMMIT" ]; then
  should_build=0
else
  changed_files="$(git diff --name-only "$LAST_DEPLOY_COMMIT" "$CURRENT_COMMIT" || true)"
  if echo "$changed_files" | grep -Eq '^(build/Dockerfile|Dockerfile|requirements[^/]*\.txt|requirements/|pyproject\.toml|poetry\.lock)'; then
    should_build=1
    build_reason="image build inputs changed"
  fi
fi

mkdir -p data backups

install_auto_update_cron() {
  if ! command -v crontab >/dev/null 2>&1; then
    echo "crontab command not found; skipping auto-update cron installation" >&2
    return 0
  fi

  begin_marker="# BEGIN AI_NEWS_AUTO_UPDATE"
  end_marker="# END AI_NEWS_AUTO_UPDATE"
  docker_bin="$(command -v docker || printf '%s' docker)"
  flock_bin=""
  if command -v flock >/dev/null 2>&1; then
    flock_bin="$(command -v flock)"
  fi

  tmp_existing="$(mktemp)"
  tmp_new="$(mktemp)"
  cleanup_cron_tmp() {
    rm -f "$tmp_existing" "$tmp_new"
  }
  trap cleanup_cron_tmp EXIT INT TERM

  crontab -l >"$tmp_existing" 2>/dev/null || true
  sed "/^${begin_marker}\$/,/^${end_marker}\$/d" "$tmp_existing" >"$tmp_new"

  if [ "$AUTO_UPDATE_ENABLED" = "1" ]; then
    cron_cmd="cd $ROOT_DIR && "
    if [ -n "$flock_bin" ]; then
      cron_cmd="${cron_cmd}${flock_bin} -n /tmp/ai-news-auto-update.lock "
    fi
    cron_cmd="${cron_cmd}${docker_bin} compose -f $COMPOSE_FILE run --rm"
    cron_cmd="${cron_cmd} -e AINEWS_CONCURRENCY_LIMIT=$AUTO_UPDATE_CONCURRENCY_LIMIT"
    cron_cmd="${cron_cmd} -e AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT=$AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT"
    cron_cmd="${cron_cmd} app ai-news fetch --once >> $AUTO_UPDATE_LOG_PATH 2>&1"

    {
      printf '\n%s\n' "$begin_marker"
      printf '# Managed by scripts/deploy_prod.sh\n'
      printf '%s %s\n' "$AUTO_UPDATE_CRON_SCHEDULE" "$cron_cmd"
      printf '%s\n' "$end_marker"
    } >>"$tmp_new"
    echo "Installed/updated auto-update cron (${AUTO_UPDATE_CRON_SCHEDULE})"
  else
    echo "AUTO_UPDATE_ENABLED=0; removed managed auto-update cron block (if present)"
  fi

  crontab "$tmp_new"
  trap - EXIT INT TERM
  cleanup_cron_tmp
}

echo "Starting PostgreSQL..."
docker compose -f "$COMPOSE_FILE" up -d db

echo "Waiting for PostgreSQL readiness..."
attempt=0
until docker compose -f "$COMPOSE_FILE" exec -T db sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "PostgreSQL did not become ready in time" >&2
    exit 1
  fi
  sleep 2
done

if [ "$should_build" -eq 1 ]; then
  echo "Building and starting app (${build_reason})..."
  docker compose -f "$COMPOSE_FILE" up -d --build app caddy
else
  echo "Starting app without rebuild (no build input changes detected)..."
  docker compose -f "$COMPOSE_FILE" up -d app caddy
fi

echo "Running migrations..."
docker compose -f "$COMPOSE_FILE" run --rm app alembic upgrade head

echo "Applying retention policy..."
docker compose -f "$COMPOSE_FILE" run --rm app ai-news prune --older-than-days "$RETENTION_DAYS"

echo "Restarting app..."
docker compose -f "$COMPOSE_FILE" up -d app caddy

echo "Checking app health..."
attempt=0
until docker compose -f "$COMPOSE_FILE" exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3)" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "App healthcheck failed" >&2
    exit 1
  fi
  sleep 2
done

if [ -n "${CADDY_SITE_ADDRESS:-}" ] && [ "${CADDY_SITE_ADDRESS}" != "localhost" ]; then
  echo "Checking HTTPS endpoint health via Caddy..."
  attempt=0
  until curl -fsS "https://${CADDY_SITE_ADDRESS}/health" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
      echo "HTTPS healthcheck via Caddy failed" >&2
      exit 1
    fi
    sleep 2
  done
fi

install_auto_update_cron

printf '%s\n' "$CURRENT_COMMIT" > "$LAST_DEPLOY_FILE"

echo "Deployment completed successfully."
