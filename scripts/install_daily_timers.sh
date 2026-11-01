#!/usr/bin/env sh
set -eu
ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
UNIT_DIR="${AINEWS_SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
command -v systemctl >/dev/null || { echo 'systemd is required for UTC scheduling' >&2; exit 1; }
# A non-root deploy user stages the units and installs them with sudo (see the sudoers sample
# deploy/sudoers.d/ai-news-deploy). An explicit AINEWS_SYSTEMD_UNIT_DIR always writes directly.
SUDO=""
STAGE_DIR=""
if [ "$(id -u)" -ne 0 ] && [ -z "${AINEWS_SYSTEMD_UNIT_DIR:-}" ]; then
  SUDO="sudo -n"
  STAGE_DIR=/var/tmp/ai-news-units
  rm -rf "$STAGE_DIR"
  mkdir -m 700 "$STAGE_DIR"
  FINAL_DIR="$UNIT_DIR"
  UNIT_DIR="$STAGE_DIR"
fi
mkdir -p "$UNIT_DIR"
for job in fetch digest; do
  case "$job" in fetch) hour=01;; digest) hour=02;; esac
  cat > "$UNIT_DIR/ai-news-daily-${job}.service" <<EOF
[Unit]
Description=AI News daily ${job} for the completed previous UTC day
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
WorkingDirectory=$ROOT_DIR
ExecStart=/bin/sh $ROOT_DIR/scripts/run_daily_${job}_job.sh
TimeoutStartSec=14400
StandardOutput=append:$ROOT_DIR/logs/daily-${job}.log
StandardError=append:$ROOT_DIR/logs/daily-${job}.log
EOF
  cat > "$UNIT_DIR/ai-news-daily-${job}.timer" <<EOF
[Unit]
Description=AI News daily ${job} in UTC (independent of host DST)
[Timer]
OnCalendar=*-*-* ${hour}:00:00 UTC
AccuracySec=1s
Persistent=false
[Install]
WantedBy=timers.target
EOF
done
# Archive capture (spec 016): after fetch and digest, with its own shorter limit and log.
cat > "$UNIT_DIR/ai-news-daily-archive.service" <<EOF
[Unit]
Description=AI News nightly archive capture of collected article text
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
WorkingDirectory=$ROOT_DIR
ExecStart=/bin/sh $ROOT_DIR/scripts/run_daily_archive_job.sh
TimeoutStartSec=3600
StandardOutput=append:$ROOT_DIR/logs/daily-archive.log
StandardError=append:$ROOT_DIR/logs/daily-archive.log
EOF
cat > "$UNIT_DIR/ai-news-daily-archive.timer" <<EOF
[Unit]
Description=AI News nightly archive capture in UTC (independent of host DST)
[Timer]
OnCalendar=*-*-* 03:00:00 UTC
AccuracySec=1s
Persistent=false
[Install]
WantedBy=timers.target
EOF
# World news job (spec 018, item 5): after archive; the script itself is off unless
# AINEWS_WORLD_COLLECT_ENABLED is true, so installing the timer downloads nothing. TimeoutStartSec
# covers the lock wait and the step limits of run_daily_world_job.sh (checked by a test).
cat > "$UNIT_DIR/ai-news-daily-world.service" <<EOF
[Unit]
Description=AI News nightly world news job: GDELT collect, Jev screen, page texts
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
WorkingDirectory=$ROOT_DIR
ExecStart=/bin/sh $ROOT_DIR/scripts/run_daily_world_job.sh
TimeoutStartSec=9600
StandardOutput=append:$ROOT_DIR/logs/daily-world.log
StandardError=append:$ROOT_DIR/logs/daily-world.log
EOF
cat > "$UNIT_DIR/ai-news-daily-world.timer" <<EOF
[Unit]
Description=AI News nightly world news collect in UTC (independent of host DST)
[Timer]
OnCalendar=*-*-* 04:00:00 UTC
AccuracySec=1s
Persistent=false
[Install]
WantedBy=timers.target
EOF
if [ -n "$STAGE_DIR" ]; then
  for unit in "$STAGE_DIR"/*; do
    $SUDO install -m 0644 "$unit" "$FINAL_DIR/$(basename "$unit")"
  done
  rm -rf "$STAGE_DIR"
fi
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now ai-news-daily-fetch.timer ai-news-daily-digest.timer
$SUDO systemctl enable --now ai-news-daily-archive.timer
$SUDO systemctl enable --now ai-news-daily-world.timer
