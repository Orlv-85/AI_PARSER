import os
import re
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
        "enable --now ai-news-daily-fetch.timer ai-news-daily-digest.timer",
        "enable --now ai-news-daily-archive.timer",
        "enable --now ai-news-daily-world.timer",
        "enable --now ai-news-daily-bulletin.timer"]


def _install(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "install_daily_timers.sh"
    script.write_text(Path("scripts/install_daily_timers.sh").read_text(encoding="utf-8"),
                      encoding="utf-8")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    systemctl = binaries / "systemctl"
    systemctl.write_text("#!/bin/sh\nexit 0\n")
    systemctl.chmod(0o755)
    units = tmp_path / "units"
    subprocess.run(["sh", str(script)], check=True, env={**os.environ,
        "PATH": str(binaries) + ":/usr/bin:/bin", "AINEWS_SYSTEMD_UNIT_DIR": str(units)})
    return tmp_path, units


def test_install_timers_includes_world(tmp_path):
    root, units = _install(tmp_path)
    service = (units / "ai-news-daily-world.service").read_text()
    assert f"ExecStart=/bin/sh {root}/scripts/run_daily_world_job.sh\n" in service
    assert "TimeoutStartSec=9600\n" in service
    assert f"StandardOutput=append:{root}/logs/daily-world.log\n" in service
    assert f"StandardError=append:{root}/logs/daily-world.log\n" in service
    timer = (units / "ai-news-daily-world.timer").read_text()
    assert "OnCalendar=*-*-* 04:00:00 UTC\n" in timer
    assert "Persistent=false\n" in timer


def _timer_start_seconds(timer):
    clock = re.search(r"^OnCalendar=\S+ (\d+):(\d+):(\d+) UTC$", timer, re.M)
    return sum(int(value) * scale for value, scale in zip(clock.groups(), (3600, 60, 1),
                                                         strict=True))


def test_bulletin_timer_runs_after_the_world_job(tmp_path):
    root, units = _install(tmp_path)
    service = (units / "ai-news-daily-bulletin.service").read_text()
    assert f"ExecStart=/bin/sh {root}/scripts/run_daily_bulletin_job.sh\n" in service
    assert f"StandardOutput=append:{root}/logs/daily-bulletin.log\n" in service
    assert f"StandardError=append:{root}/logs/daily-bulletin.log\n" in service
    timer = (units / "ai-news-daily-bulletin.timer").read_text()
    assert "OnCalendar=*-*-* 04:30:00 UTC\n" in timer
    assert "Persistent=false\n" in timer and "AccuracySec=1s\n" in timer
    world_timer = (units / "ai-news-daily-world.timer").read_text()
    assert "04:00:00 UTC" in world_timer
    script = Path("scripts/run_daily_bulletin_job.sh").read_text(encoding="utf-8")
    world = Path("scripts/run_daily_world_job.sh").read_text(encoding="utf-8")
    lock = re.search(r"^LOCK=(.+)$", script, re.M).group(1)
    assert f"LOCK={lock}\n" in world
    wait = int(re.search(r"^LOCK_WAIT=(\d+)", script, re.M).group(1))
    world_service = (units / "ai-news-daily-world.service").read_text()
    world_limit = int(re.search(r"TimeoutStartSec=(\d+)", world_service).group(1))
    assert _timer_start_seconds(timer) + wait >= _timer_start_seconds(world_timer) + world_limit


def _bulletin_job_budget(script):
    values = {name: int(value) for name, value in re.findall(r"^([A-Z_]+)=(\d+)", script, re.M)}
    step_limit = re.search(r'^run_step \S+ "\$([A-Z_]+)"', script, re.M).group(1)
    values["limit"] = values[step_limit]
    timeouts = re.findall(r'\btimeout -k (\d+) (\d+|"\$\w+")', script)
    assert len(timeouts) == script.count("timeout -k ")
    return values["LOCK_WAIT"] + sum(
        int(grace) + (values[limit[2:-1]] if limit.startswith('"$') else int(limit))
        for grace, limit in timeouts)


def test_bulletin_service_timeout_covers_lock_wait_and_steps(tmp_path):
    _, units = _install(tmp_path)
    script = Path("scripts/run_daily_bulletin_job.sh").read_text(encoding="utf-8")
    service = (units / "ai-news-daily-bulletin.service").read_text()
    unit = int(re.search(r"TimeoutStartSec=(\d+)", service).group(1))
    assert _bulletin_job_budget(script) < unit


def test_install_timers_includes_archive(tmp_path):
    root, units = _install(tmp_path)
    service = (units / "ai-news-daily-archive.service").read_text()
    assert f"ExecStart=/bin/sh {root}/scripts/run_daily_archive_job.sh\n" in service
    assert "TimeoutStartSec=3600\n" in service
    assert f"StandardOutput=append:{root}/logs/daily-archive.log\n" in service
    assert f"StandardError=append:{root}/logs/daily-archive.log\n" in service
    timer = (units / "ai-news-daily-archive.timer").read_text()
    assert "OnCalendar=*-*-* 03:00:00 UTC\n" in timer
    assert "Persistent=false\n" in timer
    # Fetch and digest units are unchanged byte for byte.
    for job, hour in (("fetch", "01"), ("digest", "02")):
        assert (units / f"ai-news-daily-{job}.service").read_text() == (
            "[Unit]\n"
            f"Description=AI News daily {job} for the completed previous UTC day\n"
            "After=docker.service network-online.target\n"
            "Requires=docker.service\n"
            "[Service]\n"
            "Type=oneshot\n"
            f"WorkingDirectory={root}\n"
            f"ExecStart=/bin/sh {root}/scripts/run_daily_{job}_job.sh\n"
            "TimeoutStartSec=14400\n"
            f"StandardOutput=append:{root}/logs/daily-{job}.log\n"
            f"StandardError=append:{root}/logs/daily-{job}.log\n")
        assert (units / f"ai-news-daily-{job}.timer").read_text() == (
            "[Unit]\n"
            f"Description=AI News daily {job} in UTC (independent of host DST)\n"
            "[Timer]\n"
            f"OnCalendar=*-*-* {hour}:00:00 UTC\n"
            "AccuracySec=1s\n"
            "Persistent=false\n"
            "[Install]\n"
            "WantedBy=timers.target\n")
