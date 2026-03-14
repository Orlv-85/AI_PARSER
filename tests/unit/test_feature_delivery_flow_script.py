from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_mock_start_script(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
repo=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -C)
      repo="$2"
      shift 2
      ;;
    --json)
      shift
      ;;
    *)
      shift
      ;;
  esac
done
mkdir -p "$repo/specs/001-test-feature"
touch "$repo/specs/001-test-feature/spec.md"
touch "$repo/specs/001-test-feature/plan.md"
touch "$repo/specs/001-test-feature/tasks.md"
touch "$repo/specs/001-test-feature/execution_packet.md"
python3 - "$repo" <<'PY'
import json
import sys
repo = sys.argv[1]
payload = {
    "status": "ok",
    "branch": "001-test-feature",
    "feature_num": "001",
    "spec_file": f"{repo}/specs/001-test-feature/spec.md",
    "plan_file": f"{repo}/specs/001-test-feature/plan.md",
    "tasks_file": f"{repo}/specs/001-test-feature/tasks.md",
    "intake_json": f"{repo}/tmp/feature_intake/x/intake.json",
    "intake_md": f"{repo}/tmp/feature_intake/x/intake.md",
    "spec_intake": f"{repo}/specs/001-test-feature/spec-intake.md",
    "execution_packet": f"{repo}/specs/001-test-feature/execution_packet.md",
}
print(json.dumps(payload))
PY
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_mock_multiagent_script(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
repo=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -C)
      repo="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
mkdir -p "$repo/tmp"
printf 'PASS\nmock\n' > "$repo/tmp/agent_audit.txt"
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_flow_bootstrap_stores_latest_state(tmp_path: Path) -> None:
    script = _repo_root() / "scripts" / "feature_delivery_flow.sh"
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()

    mock_start = tmp_path / "mock_start.sh"
    mock_run = tmp_path / "mock_run.sh"
    _write_mock_start_script(mock_start)
    _write_mock_multiagent_script(mock_run)

    result = subprocess.run(
        [
            str(script),
            "bootstrap",
            "-C",
            str(fake_repo),
            "--json",
            "--start-script",
            str(mock_start),
            "--multiagent-script",
            str(mock_run),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["branch"] == "001-test-feature"
    assert (fake_repo / "tmp" / "feature_flow" / "latest_bootstrap.json").exists()


def test_flow_run_requires_explicit_approval(tmp_path: Path) -> None:
    script = _repo_root() / "scripts" / "feature_delivery_flow.sh"
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()

    feature_dir = fake_repo / "specs" / "001-test-feature"
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text("# spec\n", encoding="utf-8")
    (feature_dir / "plan.md").write_text("# plan\n", encoding="utf-8")
    (feature_dir / "tasks.md").write_text("# tasks\n", encoding="utf-8")
    (feature_dir / "execution_packet.md").write_text("# packet\n", encoding="utf-8")

    mock_start = tmp_path / "mock_start.sh"
    mock_run = tmp_path / "mock_run.sh"
    _write_mock_start_script(mock_start)
    _write_mock_multiagent_script(mock_run)

    result = subprocess.run(
        [
            str(script),
            "run",
            "-C",
            str(fake_repo),
            "--feature-dir",
            str(feature_dir),
            "--task",
            "Implement X",
            "--allow",
            "src/app,tests",
            "--start-script",
            str(mock_start),
            "--multiagent-script",
            str(mock_run),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--approved" in result.stderr


def test_flow_run_executes_with_approval(tmp_path: Path) -> None:
    script = _repo_root() / "scripts" / "feature_delivery_flow.sh"
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()

    feature_dir = fake_repo / "specs" / "001-test-feature"
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text("# spec\n", encoding="utf-8")
    (feature_dir / "plan.md").write_text("# plan\n", encoding="utf-8")
    (feature_dir / "tasks.md").write_text("# tasks\n", encoding="utf-8")
    (feature_dir / "execution_packet.md").write_text("# packet\n", encoding="utf-8")

    mock_start = tmp_path / "mock_start.sh"
    mock_run = tmp_path / "mock_run.sh"
    _write_mock_start_script(mock_start)
    _write_mock_multiagent_script(mock_run)

    result = subprocess.run(
        [
            str(script),
            "run",
            "-C",
            str(fake_repo),
            "--feature-dir",
            str(feature_dir),
            "--task",
            "Implement X",
            "--allow",
            "src/app,tests",
            "--approved",
            "--start-script",
            str(mock_start),
            "--multiagent-script",
            str(mock_run),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "run: ok" in result.stdout
    flow_dirs = list((fake_repo / "tmp" / "feature_flow").glob("*_flow_*"))
    assert flow_dirs
