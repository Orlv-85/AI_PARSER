import os
import subprocess
from pathlib import Path


def test_timers_use_explicit_utc_and_do_not_launch_on_install(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "install_daily_timers.sh"
    script.write_text(Path("scripts/install_daily_timers.sh").read_text(encoding="utf-8"),
                      encoding="utf-8")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    systemctl = binaries / "systemctl"
    systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_SYSTEMCTL_LOG"\n')
    systemctl.chmod(0o755)
    units = tmp_path / "units"
    log = tmp_path / "systemctl.log"
    subprocess.run(["sh", str(script)], check=True, env={**os.environ,
        "PATH": str(binaries) + ":/usr/bin:/bin", "AINEWS_SYSTEMD_UNIT_DIR": str(units),
        "TEST_SYSTEMCTL_LOG": str(log)})
    for job, hour in (("fetch", "01"), ("digest", "02")):
        timer = (units / f"ai-news-daily-{job}.timer").read_text()
        assert f"OnCalendar=*-*-* {hour}:00:00 UTC" in timer
        assert "Persistent=false" in timer
        service = (units / f"ai-news-daily-{job}.service").read_text()
        assert f"ExecStart=/bin/sh {scripts}/run_daily_{job}_job.sh" in service
    assert log.read_text().splitlines() == ["daemon-reload",
        "enable --now ai-news-daily-fetch.timer ai-news-daily-digest.timer"]
