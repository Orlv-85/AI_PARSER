import os
import subprocess
from pathlib import Path

REPO = "ghcr.io/orlv-85/ai-parser"

DOCKER_STUB = r"""#!/bin/sh
printf '%s\n' "$*" >> "$TEST_DOCKER_LOG"
case "$*" in
"images --format {{.Repository}}:{{.Tag}} $TEST_REPO") cat "$TEST_IMAGES";;
"ps -a --format {{.Image}}") cat "$TEST_IN_USE";;
"rmi $TEST_FAIL_RMI") exit 1;;
"image prune -f") test -z "$TEST_FAIL_PRUNE";;
esac
exit 0
"""


def _run_deploy(tmp_path, *, images, in_use, previous, fail_rmi="none", fail_prune="", extra_env=None):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "deploy_prod.sh"
    script.write_text(Path("scripts/deploy_prod.sh").read_text(encoding="utf-8"), encoding="utf-8")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in {
        "git": '#!/bin/sh\nif [ "$1" = rev-parse ]; then echo test-commit; fi\n',
        "docker": DOCKER_STUB,
        "crontab": "#!/bin/sh\nexit 0\n",
    }.items():
        (binaries / name).write_text(body, encoding="utf-8")
        (binaries / name).chmod(0o755)
    (tmp_path / "images.txt").write_text("\n".join(images) + "\n", encoding="utf-8")
    (tmp_path / "in_use.txt").write_text("\n".join(in_use) + "\n", encoding="utf-8")
    if previous:
        (tmp_path / ".last_deploy_image").write_text(previous + "\n", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{binaries}:/usr/bin:/bin",
        "TEST_DOCKER_LOG": str(tmp_path / "docker.log"),
        "TEST_IMAGES": str(tmp_path / "images.txt"),
        "TEST_IN_USE": str(tmp_path / "in_use.txt"),
        "TEST_REPO": REPO,
        "TEST_FAIL_RMI": fail_rmi,
        "TEST_FAIL_PRUNE": fail_prune,
        "CADDY_SITE_ADDRESS": "localhost",
        "AINEWS_DAILY_SCHEDULER": "cron",
        "AUTO_UPDATE_ENABLED": "0",
        "AINEWS_DIGEST_CRON_ENABLED": "0",
        "APP_IMAGE": f"{REPO}:v3",
        **(extra_env or {}),
    }
    result = subprocess.run(
        ["sh", str(script), "v3"], env=env, capture_output=True, text=True, check=False
    )
    calls = (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()
    return result, calls


def _removed(calls):
    return [call.removeprefix("rmi ") for call in calls if call.startswith("rmi ")]


def test_deploy_prunes_old_release_images_but_keeps_current_previous_and_in_use(tmp_path) -> None:
    result, calls = _run_deploy(
        tmp_path,
        images=[f"{REPO}:v3", f"{REPO}:v2", f"{REPO}:v1", f"{REPO}:v0", f"{REPO}:latest", f"{REPO}:<none>"],
        in_use=[f"{REPO}:v1", "postgres:18-alpine"],
        previous=f"{REPO}:v2",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _removed(calls) == [f"{REPO}:v0"]
    assert "image prune -f" in calls
    assert not any("volume" in call for call in calls)
    assert (tmp_path / ".last_deploy_image").read_text(encoding="utf-8").strip() == f"{REPO}:v3"


def test_deploy_never_removes_non_project_images(tmp_path) -> None:
    result, calls = _run_deploy(
        tmp_path,
        images=["amnezia-awg2:latest", "postgres:18-alpine", "caddy:2-alpine", f"{REPO}-other:v1"],
        in_use=[],
        previous="",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _removed(calls) == []


def test_deploy_succeeds_when_image_prune_fails(tmp_path) -> None:
    result, calls = _run_deploy(
        tmp_path,
        images=[f"{REPO}:v3", f"{REPO}:v0"],
        in_use=[],
        previous=f"{REPO}:v2",
        fail_rmi=f"{REPO}:v0",
        fail_prune="1",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Deployment completed successfully." in result.stdout
    assert f"rmi {REPO}:v0" in calls


def test_deploy_image_prune_can_be_disabled(tmp_path) -> None:
    result, calls = _run_deploy(
        tmp_path,
        images=[f"{REPO}:v3", f"{REPO}:v0"],
        in_use=[],
        previous=f"{REPO}:v2",
        extra_env={"IMAGE_PRUNE_ENABLED": "0"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _removed(calls) == []
    assert "image prune -f" not in calls
