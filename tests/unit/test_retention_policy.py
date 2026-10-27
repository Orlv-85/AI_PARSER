import os
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import app.cli.main as cli_main


@pytest.mark.parametrize("stored,override,expected", [
    (None, None, 800), (800, None, 800), ("'900' # server override", None, 900),
    (100, "800", 800),
])
def test_maintenance_default_server_config_and_explicit_override(
    tmp_path, stored, override, expected,
):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "db_maintenance.sh"
    script.write_text(Path("scripts/db_maintenance.sh").read_text(encoding="utf-8"))
    if stored is not None:
        (tmp_path / ".env").write_text(f"RETENTION_DAYS={stored}\n")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LOG"\n'
                      'case "$*" in *pg_database_size*) echo 1000000;; esac\n')
    docker.chmod(0o755)
    environment = {**os.environ, "PATH": f"{binaries}:/usr/bin:/bin",
                   "TEST_LOG": str(tmp_path / "calls")}
    environment.pop("RETENTION_DAYS", None)
    if override is not None:
        environment["RETENTION_DAYS"] = override
    result = subprocess.run(["sh", str(script)], env=environment, capture_output=True,
                            text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"app ai-news prune --older-than-days {expected}" in (tmp_path / "calls").read_text()
    assert "tightening retention" not in result.stdout


def _run_size_loop(tmp_path, sizes):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "db_maintenance.sh"
    script.write_text(Path("scripts/db_maintenance.sh").read_text(encoding="utf-8"))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (tmp_path / "sizes").write_text("\n".join(str(size) for size in sizes) + "\n")
    docker = binaries / "docker"
    # Each size query pops the next value; the last one repeats.
    docker.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LOG"\n'
        'case "$*" in *pg_database_size*)\n'
        '  head -n 1 "$TEST_SIZES"\n'
        '  [ "$(wc -l < "$TEST_SIZES")" -gt 1 ] && sed -i.bak 1d "$TEST_SIZES";;\n'
        'esac\n')
    docker.chmod(0o755)
    environment = {**os.environ, "PATH": f"{binaries}:/usr/bin:/bin",
                   "TEST_LOG": str(tmp_path / "calls"), "TEST_SIZES": str(tmp_path / "sizes"),
                   "RETENTION_DAYS": "30"}
    result = subprocess.run(["sh", str(script)], env=environment, capture_output=True,
                            text=True, check=False)
    calls = (tmp_path / "calls").read_text().count("ai-news prune")
    return result, calls


def test_size_loop_stops_when_prune_does_not_reduce_size(tmp_path):
    gb = 1024 ** 3
    # Archive-before-prune: the size stays above the limit however far retention is lowered.
    result, prunes = _run_size_loop(tmp_path, [6 * gb])
    assert result.returncode == 0, result.stdout + result.stderr
    assert prunes == 2  # configured retention, then one tightening step
    assert "did not reduce DB size" in result.stderr


def test_size_loop_keeps_tightening_while_size_drops(tmp_path):
    gb = 1024 ** 3
    result, prunes = _run_size_loop(tmp_path, [6 * gb, 5 * gb, 3 * gb])
    assert result.returncode == 0, result.stdout + result.stderr
    assert prunes == 3
    assert "did not reduce" not in result.stderr


def test_maintenance_prunes_with_last_deployed_image(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "db_maintenance.sh"
    script.write_text(Path("scripts/db_maintenance.sh").read_text(encoding="utf-8"))
    (tmp_path / ".last_deploy_image").write_text("release:tested\n", encoding="utf-8")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s %s\\n" "${APP_IMAGE:-none}" "$*" >> "$TEST_LOG"\n'
                      'case "$*" in *pg_database_size*) echo 1000000;; esac\n')
    docker.chmod(0o755)
    environment = {**os.environ, "PATH": f"{binaries}:/usr/bin:/bin",
                   "TEST_LOG": str(tmp_path / "calls")}
    environment.pop("APP_IMAGE", None)
    result = subprocess.run(["sh", str(script)], env=environment, capture_output=True,
                            text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "release:tested compose -f docker-compose.prod.yml run --rm app ai-news prune" in (
        tmp_path / "calls").read_text()


def test_cli_default_and_explicit_retention_remain_compatible(monkeypatch):
    calls = []

    class TestSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class TestRepo:
        def __init__(self, _session):
            pass

        def count_older_than(self, *, older_than_days):
            calls.append(older_than_days)
            return 0

    monkeypatch.setattr(cli_main, "create_all", lambda: None)
    monkeypatch.setattr(cli_main, "SessionLocal", TestSession)
    monkeypatch.setattr(cli_main, "ArticleRepo", TestRepo)
    runner = CliRunner()
    assert runner.invoke(cli_main.app, ["prune", "--dry-run"]).exit_code == 0
    assert runner.invoke(cli_main.app, ["prune", "--dry-run", "--older-than-days", "100"
                                      ]).exit_code == 0
    assert calls == [800, 100]


def test_next_deploy_and_maintenance_workflows_pin_retention_override():
    for file, step_name in (
        ("deploy-release.yml", "Deploy tagged release"),
        ("deploy-by-tag.yml", "Deploy selected tag"),
        ("db-maintenance.yml", "Run maintenance and backup"),
    ):
        workflow = yaml.safe_load((Path(".github/workflows") / file).read_text())
        steps = [step for job in workflow["jobs"].values() for step in job["steps"]]
        deploy = next(step for step in steps if step.get("name") == step_name)
        assert deploy["env"]["RETENTION_DAYS"] == "${{ vars.RETENTION_DAYS || '800' }}"
        assert "RETENTION_DAYS='${RETENTION_DAYS}'" in deploy["run"]
        if file != "db-maintenance.yml":
            payload = next(step for step in steps if step.get("name") ==
                           "Prepare runtime env payload")
            assert "printf 'RETENTION_DAYS=%s" in payload["run"]
            assert "AINEWS_DIGEST_MODEL|RETENTION_DAYS)=" in deploy["run"]
    sample = (Path("deploy") / ".env.prod.example").read_text()
    assert "RETENTION_DAYS=800\n" in sample
    assert "DB_MAX_SIZE_GB=5\n" in sample
    assert 'DB_MAX_SIZE_GB="${DB_MAX_SIZE_GB:-5}"' in Path("scripts/db_maintenance.sh").read_text(
        encoding="utf-8")
