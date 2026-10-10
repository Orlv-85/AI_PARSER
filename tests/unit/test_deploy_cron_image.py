import os
import subprocess
from pathlib import Path


def test_deploy_updates_cron_to_use_the_deployed_image(tmp_path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "deploy_prod.sh"
    script.write_text(Path("scripts/deploy_prod.sh").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text("APP_IMAGE=stale:latest\n", encoding="utf-8")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    cron_store = tmp_path / "crontab"
    cron_store.write_text("0 0 * * * echo keep-existing-job\n", encoding="utf-8")
    commands = {
        "git": '#!/bin/sh\nif [ "$1" = rev-parse ]; then echo test-commit; fi\n',
        "docker": '#!/bin/sh\nprintf "%s|%s\\n" "$APP_IMAGE" "$*" >> "$TEST_DOCKER_LOG"\n',
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
        "POCKETPAW_ENABLED": "0",
        "ANTIGRAVITY_ENABLED": "0",
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
        assert "stop antigravity" in calls
        assert "exec ai-news-app python" in calls
        assert "exec -T app python" not in calls
