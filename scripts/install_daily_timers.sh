#!/usr/bin/env sh
set -eu
ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
UNIT_DIR="${AINEWS_SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
command -v systemctl >/dev/null || { echo 'systemd is required for UTC scheduling' >&2; exit 1; }
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
systemctl daemon-reload
systemctl enable --now ai-news-daily-fetch.timer ai-news-daily-digest.timer
