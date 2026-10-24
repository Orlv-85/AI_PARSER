#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
if [ -z "${RETENTION_DAYS:-}" ] && [ -f .env ]; then
  RETENTION_DAYS="$(sed -nE "s/^[[:space:]]*(export[[:space:]]+)?RETENTION_DAYS[[:space:]]*=[[:space:]]*['\"]?([0-9]+)['\"]?([[:space:]]*#.*)?[[:space:]]*$/\\2/p" .env | tail -n 1)"
fi
RETENTION_DAYS="${RETENTION_DAYS:-800}"
DEPLOY_TAG="${1:-}"
LAST_DEPLOY_FILE="${LAST_DEPLOY_FILE:-.last_deploy_commit}"
LAST_DEPLOY_IMAGE_FILE="${LAST_DEPLOY_IMAGE_FILE:-.last_deploy_image}"
APP_IMAGE_REPO="${APP_IMAGE_REPO:-ghcr.io/orlv-85/ai-parser}"
APP_IMAGE="${APP_IMAGE:-}"
AUTO_UPDATE_ENABLED="${AUTO_UPDATE_ENABLED:-1}"
AUTO_UPDATE_CRON_SCHEDULE="${AUTO_UPDATE_CRON_SCHEDULE:-0 1 * * *}"
AUTO_UPDATE_LOG_PATH="${AUTO_UPDATE_LOG_PATH:-/var/log/ai-news-auto-update.log}"
AUTO_UPDATE_CONCURRENCY_LIMIT="${AUTO_UPDATE_CONCURRENCY_LIMIT:-10}"
AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT="${AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT:-4}"
AUTO_UPDATE_RSS_EXTRACT_FULL_TEXT="${AUTO_UPDATE_RSS_EXTRACT_FULL_TEXT:-0}"
AINEWS_DAILY_SCHEDULER="${AINEWS_DAILY_SCHEDULER:-systemd}"
FETCH_TIMER_ENABLED="$AUTO_UPDATE_ENABLED"
DIGEST_TIMER_ENABLED="${AINEWS_DIGEST_CRON_ENABLED:-1}"
if [ "$AINEWS_DAILY_SCHEDULER" = systemd ]; then
  AUTO_UPDATE_ENABLED=0
  AINEWS_DIGEST_CRON_ENABLED=0
fi
AINEWS_DIGEST_CRON_ENABLED="${AINEWS_DIGEST_CRON_ENABLED:-1}"
AINEWS_DIGEST_CRON_SCHEDULE="${AINEWS_DIGEST_CRON_SCHEDULE:-0 2 * * *}"
AINEWS_DIGEST_LOG_PATH="${AINEWS_DIGEST_LOG_PATH:-$ROOT_DIR/logs/daily-digest.log}"
AINEWS_WEEKLY_CRON_ENABLED="${AINEWS_WEEKLY_CRON_ENABLED:-0}"
AINEWS_WEEKLY_CRON_SCHEDULE="${AINEWS_WEEKLY_CRON_SCHEDULE:-15 2 * * 1}"
AINEWS_WEEKLY_LOG_PATH="${AINEWS_WEEKLY_LOG_PATH:-$ROOT_DIR/logs/weekly-analytics.log}"

if [ -n "$DEPLOY_TAG" ]; then
  echo "Checking out tag: $DEPLOY_TAG"
  git fetch --tags origin
  git checkout --force "$DEPLOY_TAG"
fi

if [ -z "$APP_IMAGE" ]; then
  if [ -n "$DEPLOY_TAG" ]; then
    APP_IMAGE="${APP_IMAGE_REPO}:${DEPLOY_TAG}"
  else
    APP_IMAGE="${APP_IMAGE_REPO}:latest"
  fi
fi
export APP_IMAGE

CURRENT_COMMIT="$(git rev-parse --verify HEAD)"

mkdir -p data backups logs

# Retire the old proxy without deleting its bind-mounted account data.
if docker container inspect ai-news-antigravity >/dev/null 2>&1; then
  echo "Removing retired AI proxy container; persisted account data is preserved"
  docker stop ai-news-antigravity >/dev/null
  docker rm ai-news-antigravity >/dev/null
fi

# Keep the retired local tooling recoverable instead of deleting it recursively.
legacy_backup=""
for legacy_path in .tools/pocketpaw-venv .tools/pocketpaw .tools/pocketpaw-version; do
  if [ -e "$legacy_path" ] || [ -L "$legacy_path" ]; then
    if [ -z "$legacy_backup" ]; then
      legacy_backup="$(mktemp -d "$ROOT_DIR/backups/retired-ai-tools.XXXXXX")"
    fi
    mv "$legacy_path" "$legacy_backup/"
  fi
done
if [ -n "$legacy_backup" ]; then
  echo "Retired tooling archived at $legacy_backup"
fi

is_enabled() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

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

  if is_enabled "$AUTO_UPDATE_ENABLED"; then
    cron_cmd="cd $ROOT_DIR && APP_IMAGE=$APP_IMAGE "
    if [ -n "$flock_bin" ]; then
      cron_cmd="${cron_cmd}${flock_bin} -n /tmp/ai-news-auto-update.lock "
    fi
    cron_cmd="${cron_cmd}${docker_bin} compose -f $COMPOSE_FILE run --rm"
    cron_cmd="${cron_cmd} -e AINEWS_CONCURRENCY_LIMIT=$AUTO_UPDATE_CONCURRENCY_LIMIT"
    cron_cmd="${cron_cmd} -e AINEWS_RSS_FULL_TEXT_CONCURRENCY_LIMIT=$AUTO_UPDATE_FULLTEXT_CONCURRENCY_LIMIT"
    cron_cmd="${cron_cmd} -e AINEWS_RSS_EXTRACT_FULL_TEXT=$AUTO_UPDATE_RSS_EXTRACT_FULL_TEXT"
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

install_daily_digest_cron() {
  if ! command -v crontab >/dev/null 2>&1; then
    echo "crontab command not found; skipping daily digest cron installation" >&2
    return 0
  fi

  begin_marker="# BEGIN AI_NEWS_DAILY_DIGEST"
  end_marker="# END AI_NEWS_DAILY_DIGEST"

  tmp_existing="$(mktemp)"
  tmp_new="$(mktemp)"
  cleanup_cron_tmp() {
    rm -f "$tmp_existing" "$tmp_new"
  }
  trap cleanup_cron_tmp EXIT INT TERM

  crontab -l >"$tmp_existing" 2>/dev/null || true
  sed "/^${begin_marker}\$/,/^${end_marker}\$/d" "$tmp_existing" >"$tmp_new"

  if is_enabled "$AINEWS_DIGEST_CRON_ENABLED"; then
    {
      printf '\n%s\n' "$begin_marker"
      printf '# Managed by scripts/deploy_prod.sh\n'
      printf 'CRON_TZ=UTC\n'
      printf '%s cd %s && ./scripts/run_daily_digest_job.sh >> %s 2>&1\n' \
        "$AINEWS_DIGEST_CRON_SCHEDULE" "$ROOT_DIR" "$AINEWS_DIGEST_LOG_PATH"
      printf '%s\n' "$end_marker"
    } >>"$tmp_new"
    echo "Installed/updated daily digest cron (${AINEWS_DIGEST_CRON_SCHEDULE} UTC)"
  else
    echo "AINEWS_DIGEST_CRON_ENABLED=0; removed managed daily digest cron block (if present)"
  fi

  crontab "$tmp_new"
  trap - EXIT INT TERM
  cleanup_cron_tmp
}

install_weekly_analytics_cron() {
  if ! command -v crontab >/dev/null 2>&1; then
    echo "crontab command not found; skipping weekly analytics cron installation" >&2
    return 0
  fi

  begin_marker="# BEGIN AI_NEWS_WEEKLY_ANALYTICS"
  end_marker="# END AI_NEWS_WEEKLY_ANALYTICS"

  tmp_existing="$(mktemp)"
  tmp_new="$(mktemp)"
  cleanup_cron_tmp() {
    rm -f "$tmp_existing" "$tmp_new"
  }
  trap cleanup_cron_tmp EXIT INT TERM

  crontab -l >"$tmp_existing" 2>/dev/null || true
  sed "/^${begin_marker}\$/,/^${end_marker}\$/d" "$tmp_existing" >"$tmp_new"

  if is_enabled "$AINEWS_WEEKLY_CRON_ENABLED"; then
    {
      printf '\n%s\n' "$begin_marker"
      printf '# Managed by scripts/deploy_prod.sh\n'
      printf 'CRON_TZ=UTC\n'
      printf '%s cd %s && ./scripts/run_weekly_analytics_job.sh >> %s 2>&1\n' \
        "$AINEWS_WEEKLY_CRON_SCHEDULE" "$ROOT_DIR" "$AINEWS_WEEKLY_LOG_PATH"
      printf '%s\n' "$end_marker"
    } >>"$tmp_new"
    echo "Installed/updated weekly analytics cron (${AINEWS_WEEKLY_CRON_SCHEDULE} UTC)"
  else
    echo "AINEWS_WEEKLY_CRON_ENABLED=0; removed managed weekly analytics cron block (if present)"
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

echo "Deploying app image: $APP_IMAGE"
echo "Pulling app image from registry..."
docker compose -f "$COMPOSE_FILE" pull app

echo "Starting app and caddy..."
docker compose -f "$COMPOSE_FILE" up -d app caddy

echo "Running migrations..."
docker compose -f "$COMPOSE_FILE" run --rm app alembic upgrade head

echo "Applying retention policy..."
docker compose -f "$COMPOSE_FILE" run --rm app ai-news prune --older-than-days "$RETENTION_DAYS"

echo "Restarting app..."
docker compose -f "$COMPOSE_FILE" up -d app caddy

echo "Checking app health..."
attempt=0
until docker exec ai-news-app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3)" >/dev/null 2>&1; do
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

printf '%s\n' "$APP_IMAGE" > "$LAST_DEPLOY_IMAGE_FILE"
install_auto_update_cron
install_daily_digest_cron
install_weekly_analytics_cron
if [ "$AINEWS_DAILY_SCHEDULER" = systemd ]; then
  # The deploy user is not root; the sudoers file allows exactly these systemctl calls.
  SUDO=""
  if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo -n"
  fi
  sh "$ROOT_DIR/scripts/install_daily_timers.sh"
  if ! is_enabled "$FETCH_TIMER_ENABLED"; then
    $SUDO systemctl disable --now ai-news-daily-fetch.timer
  fi
  if ! is_enabled "$DIGEST_TIMER_ENABLED"; then
    $SUDO systemctl disable --now ai-news-daily-digest.timer
  fi
fi

printf '%s\n' "$CURRENT_COMMIT" > "$LAST_DEPLOY_FILE"
printf '%s\n' "$APP_IMAGE" > "$LAST_DEPLOY_IMAGE_FILE"

echo "Deployment completed successfully."
