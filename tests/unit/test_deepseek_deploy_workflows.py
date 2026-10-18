import os
import re
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
@pytest.mark.parametrize("previous_weekly_enabled", ["true", "false"])
def test_deploy_transports_deepseek_secret_privately(
    workflow, previous_weekly_enabled, tmp_path,
) -> None:
    config = yaml.safe_load(Path(".github/workflows", workflow).read_text(encoding="utf-8"))
    steps = config["jobs"]["deploy"]["steps"]
    validate = next(step for step in steps if step["name"] == "Validate deploy config")
    assert validate["env"]["DS_API_KEY"] == "${{ secrets.DS_API_KEY }}"
    assert 'test -n "${DS_API_KEY}"' in validate["run"]
    assert "secrets.DS_API_KEY" not in validate["run"]
    payload = next(step for step in steps if step["name"] == "Prepare runtime env payload")
    assert payload["env"]["DS_API_KEY"] == "${{ secrets.DS_API_KEY }}"
    assert payload["env"]["AINEWS_WEEKLY_V2_ENABLED"] == "false"
    assert payload["env"]["AINEWS_JEV_ENABLED"] == "true"
    assert payload["env"]["AINEWS_SEMANTIC_ADMISSION_ENABLED"] == "true"
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
        "AINEWS_WEEKLY_V2_ENABLED": "false",
        "AINEWS_JEV_ENABLED": "true",
        "AINEWS_SEMANTIC_ADMISSION_ENABLED": "true",
        "RETENTION_DAYS": "800",
    }
    result = subprocess.run(
        ["bash", "-c", run], env=environment, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "test-only-secret" not in result.stdout + result.stderr
    values = dict(line.split("=", 1) for line in env_path.read_text(encoding="utf-8").splitlines())
    assert values["DS_API_KEY"] == "test-only-secret"
    assert values["AINEWS_DIGEST_MODEL"] == "deepseek-flash"
    assert values["AINEWS_WEEKLY_V2_ENABLED"] == "false"
    assert values["AINEWS_JEV_ENABLED"] == "true"
    assert values["AINEWS_SEMANTIC_ADMISSION_ENABLED"] == "true"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    deploy = next(step for step in steps if "retry sshpass" in step.get("run", ""))
    assert "|DS_API_KEY|AINEWS_DIGEST_MODEL|RETENTION_DAYS)=" in deploy["run"]
    assert "chmod 600 .env.next" in deploy["run"]
    assert "AINEWS_WEEKLY_CRON_ENABLED=0 APP_IMAGE=" in deploy["run"]
    assert "POCKETPAW_ENABLED=" not in deploy["run"]
    assert "POCKETPAW_VERSION=" not in deploy["run"]
    pattern = re.search(r"grep -vE '([^']+)'", deploy["run"])
    assert pattern is not None
    previous_env = tmp_path / "previous.env"
    previous_env.write_text(
        f"AINEWS_WEEKLY_V2_ENABLED={previous_weekly_enabled}\n"
        "AINEWS_JEV_ENABLED=false\nAINEWS_SEMANTIC_ADMISSION_ENABLED=false\n"
        "JEV_API_KEY=test-only-jev\nRETENTION_DAYS=100\n", encoding="utf-8")
    filtered = subprocess.run(["grep", "-vE", pattern[1], str(previous_env)],
                              capture_output=True, text=True, check=True)
    merged = filtered.stdout + env_path.read_text(encoding="utf-8")
    for name, value in {
        "AINEWS_WEEKLY_V2_ENABLED": "false",
        "AINEWS_JEV_ENABLED": "true",
        "AINEWS_SEMANTIC_ADMISSION_ENABLED": "true",
        "RETENTION_DAYS": "800",
    }.items():
        assert merged.count(name + "=") == 1
        assert f"{name}={value}\n" in merged
    assert "JEV_API_KEY=test-only-jev\n" in merged


def test_production_compose_passes_weekly_v2_flag_to_all_app_commands() -> None:
    compose = yaml.safe_load(Path("docker-compose.prod.yml").read_text(encoding="utf-8"))
    assert compose["services"]["app"]["environment"]["AINEWS_WEEKLY_V2_ENABLED"] == (
        "${AINEWS_WEEKLY_V2_ENABLED:-false}")


@pytest.mark.parametrize("workflow", ["deploy-release.yml", "deploy-by-tag.yml"])
@pytest.mark.parametrize(
    ("secret", "expected"),
    [("publish-token-0123456789abcdef$0123", "publish-token-0123456789abcdef$$0123"), ("", "")],
)
def test_deploy_transports_publish_api_token(workflow, secret, expected, tmp_path) -> None:
    config = yaml.safe_load(Path(".github/workflows", workflow).read_text(encoding="utf-8"))
    steps = config["jobs"]["deploy"]["steps"]
    payload = next(step for step in steps if step["name"] == "Prepare runtime env payload")
    assert payload["env"]["AINEWS_PUBLISH_API_TOKEN"] == "${{ secrets.AINEWS_PUBLISH_API_TOKEN }}"
    env_path = tmp_path / "runtime.env"
    run = payload["run"].replace("/tmp/ai_news_auth.env", str(env_path))
    environment = {
        **os.environ,
        **dict.fromkeys(payload["env"], "test-only-value"),
        "AINEWS_PUBLISH_API_TOKEN": secret,
    }
    result = subprocess.run(
        ["bash", "-c", run], env=environment, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    if secret:
        assert secret not in result.stdout + result.stderr
    assert f"AINEWS_PUBLISH_API_TOKEN={expected}\n" in env_path.read_text(encoding="utf-8")

    deploy = next(step for step in steps if "retry sshpass" in step.get("run", ""))
    pattern = re.search(r"grep -vE '([^']+)'", deploy["run"])
    assert pattern is not None
    previous_env = tmp_path / "previous.env"
    previous_env.write_text(
        "AINEWS_PUBLISH_API_TOKEN=old-manual-token\nJEV_API_KEY=test-only-jev\n",
        encoding="utf-8",
    )
    filtered = subprocess.run(["grep", "-vE", pattern[1], str(previous_env)],
                              capture_output=True, text=True, check=True)
    merged = filtered.stdout + env_path.read_text(encoding="utf-8")
    assert merged.count("AINEWS_PUBLISH_API_TOKEN=") == 1
    assert "old-manual-token" not in merged
    assert "JEV_API_KEY=test-only-jev\n" in merged
