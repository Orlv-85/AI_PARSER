import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    "workflow",
    [
        "tests.yml",
        "deploy-release.yml",
        "deploy-by-tag.yml",
        "db-maintenance.yml",
    ],
)
def test_workflows_pin_runner_and_use_node24_checkout(workflow) -> None:
    config = yaml.safe_load(Path(".github/workflows", workflow).read_text(encoding="utf-8"))
    for job in config["jobs"].values():
        assert job["runs-on"] == "ubuntu-24.04"
        for step in job.get("steps", []):
            action = step.get("uses", "")
            if action.startswith("actions/checkout@"):
                assert action == "actions/checkout@v5"
            for name, version in {
                "docker/setup-buildx-action": "v4",
                "docker/login-action": "v4",
                "docker/build-push-action": "v7",
            }.items():
                if action.startswith(name + "@"):
                    assert action == name + "@" + version


@pytest.mark.parametrize("workflow", ["deploy-release.yml", "deploy-by-tag.yml"])
def test_deploy_transports_deepseek_secret_privately(workflow, tmp_path) -> None:
    config = yaml.safe_load(Path(".github/workflows", workflow).read_text(encoding="utf-8"))
    steps = config["jobs"]["deploy"]["steps"]
    validate = next(step for step in steps if step["name"] == "Validate deploy config")
    assert validate["env"]["DS_API_KEY"] == "${{ secrets.DS_API_KEY }}"
    assert 'test -n "${DS_API_KEY}"' in validate["run"]
    assert "secrets.DS_API_KEY" not in validate["run"]
    payload = next(step for step in steps if step["name"] == "Prepare runtime env payload")
    assert payload["env"]["DS_API_KEY"] == "${{ secrets.DS_API_KEY }}"
    assert not any(
        key.startswith(("ANTIGRAVITY_", "POCKETPAW_", "ANTHROPIC_")) for key in payload["env"]
    )
    env_path = tmp_path / "runtime.env"
    run = payload["run"].replace("/tmp/ai_news_auth.env", str(env_path))
    environment = {
        **os.environ,
        **dict.fromkeys(payload["env"], "test-only-value"),
        "DS_API_KEY": "test-only-secret",
        "AINEWS_DIGEST_MODEL": "deepseek-flash",
    }
    result = subprocess.run(
        ["bash", "-c", run], env=environment, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "test-only-secret" not in result.stdout + result.stderr
    values = dict(line.split("=", 1) for line in env_path.read_text(encoding="utf-8").splitlines())
    assert values["DS_API_KEY"] == "test-only-secret"
    assert values["AINEWS_DIGEST_MODEL"] == "deepseek-flash"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    deploy = next(step for step in steps if "retry sshpass" in step.get("run", ""))
    assert "|DS_API_KEY|AINEWS_DIGEST_MODEL)=" in deploy["run"]
    assert "chmod 600 .env.next" in deploy["run"]
    assert "POCKETPAW_ENABLED=" not in deploy["run"]
    assert "POCKETPAW_VERSION=" not in deploy["run"]
