import os
import subprocess
from pathlib import Path

import pytest


def _create_legacy_tooling(tmp_path) -> tuple[Path, Path]:
    legacy_tools = tmp_path / ".tools"
    legacy_bin = legacy_tools / "pocketpaw-venv" / "bin"
    legacy_bin.mkdir(parents=True)
    (legacy_bin / "pocketpaw").write_text("retired-tool", encoding="utf-8")
    (legacy_tools / "pocketpaw").symlink_to(legacy_bin / "pocketpaw")
    (legacy_tools / "pocketpaw-version").write_text("0.2.5", encoding="utf-8")
    account_data = tmp_path / "data" / "antigravity" / "accounts.json"
    account_data.parent.mkdir(parents=True)
    account_data.write_text("preserve-existing-account-data", encoding="utf-8")
    return legacy_tools, account_data


@pytest.mark.parametrize("legacy_container_present", [False, True])
def test_deploy_updates_cron_to_use_the_deployed_image(tmp_path, legacy_container_present) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "deploy_prod.sh"
    script.write_text(Path("scripts/deploy_prod.sh").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text("APP_IMAGE=stale:latest\n", encoding="utf-8")
    legacy_state = tmp_path / "legacy-container"
    if legacy_container_present:
        legacy_state.touch()
    legacy_tools, account_data = _create_legacy_tooling(tmp_path)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    cron_store = tmp_path / "crontab"
    cron_store.write_text("0 0 * * * echo keep-existing-job\n", encoding="utf-8")
    commands = {
        "git": '#!/bin/sh\nif [ "$1" = rev-parse ]; then echo test-commit; fi\n',
        "docker": (
            '#!/bin/sh\nprintf "%s|%s\\n" "$APP_IMAGE" "$*" >> "$TEST_DOCKER_LOG"\n'
            'case "$*" in\n'
            '"container inspect ai-news-antigravity") test -f "$TEST_LEGACY_STATE";;\n'
            '"rm ai-news-antigravity") rm -f "$TEST_LEGACY_STATE";;\n'
            "esac\n"
        ),
        "crontab": (
            '#!/bin/sh\nif [ "$1" = -l ]; then cat "$TEST_CRON_STORE"; '
            'else cp "$1" "$TEST_CRON_STORE"; fi\n'
        ),
        "flock": '#!/bin/sh\nshift 2\nexec "$@"\n',
    }
    for name, body in commands.items():
        binary = binaries / name
        binary.write_text(body, encoding="utf-8")
        binary.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{binaries}:/usr/bin:/bin",
        "TEST_CRON_STORE": str(cron_store),
        "TEST_DOCKER_LOG": str(tmp_path / "docker.log"),
        "TEST_LEGACY_STATE": str(legacy_state),
        "CADDY_SITE_ADDRESS": "localhost",
        "AUTO_UPDATE_LOG_PATH": str(tmp_path / "update.log"),
    }
    for tag in ("v0.1.62", "v0.1.63"):
        image = f"ghcr.io/orlv-85/ai-parser:{tag}"
        result = subprocess.run(
            ["sh", str(script), tag],
            env={**env, "APP_IMAGE": image},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        cron = cron_store.read_text(encoding="utf-8")
        assert cron.count("# BEGIN AI_NEWS_AUTO_UPDATE") == 1
        assert "echo keep-existing-job" in cron
        fetch_line = next(line for line in cron.splitlines() if "ai-news fetch --once" in line)
        command = fetch_line.split(" ", 5)[5]
        subprocess.run(["sh", "-c", command], env={**env, "APP_IMAGE": "stale:latest"}, check=True)
        last_call = (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()[-1]
        assert last_call.startswith(image + "|")
        assert last_call.endswith("app ai-news fetch --once")
        calls = (tmp_path / "docker.log").read_text(encoding="utf-8")
        assert calls.count("|stop ai-news-antigravity\n") == int(legacy_container_present)
        assert calls.count("|rm ai-news-antigravity\n") == int(legacy_container_present)
        assert "--volumes" not in calls
        assert "up -d antigravity" not in calls
        assert "pull app antigravity" not in calls
        assert "exec ai-news-app python" in calls
        assert "exec -T app python" not in calls
        archives = list((tmp_path / "backups").glob("retired-ai-tools.*"))
        assert len(archives) == 1
        assert (archives[0] / "pocketpaw-venv" / "bin" / "pocketpaw").read_text(
            encoding="utf-8"
        ) == "retired-tool"
        assert (archives[0] / "pocketpaw").is_symlink()
        assert (archives[0] / "pocketpaw-version").read_text(encoding="utf-8") == "0.2.5"
        assert account_data.read_text(encoding="utf-8") == "preserve-existing-account-data"
        assert not (legacy_tools / "pocketpaw-venv").exists()
        assert not (legacy_tools / "pocketpaw").is_symlink()
