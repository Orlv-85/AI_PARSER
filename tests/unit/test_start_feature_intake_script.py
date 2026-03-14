from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_fake_specify(repo: Path) -> None:
    scripts_dir = repo / ".specify" / "scripts" / "bash"
    templates_dir = repo / ".specify" / "templates"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)

    (templates_dir / "tasks-template.md").write_text("# Tasks template\n", encoding="utf-8")

    create_script = scripts_dir / "create-new-feature.sh"
    create_script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
mkdir -p specs/001-test-feature
spec_file="$(pwd)/specs/001-test-feature/spec.md"
touch "$spec_file"
printf '{"BRANCH_NAME":"001-test-feature","SPEC_FILE":"%s","FEATURE_NUM":"001"}\n' "$spec_file"
""",
        encoding="utf-8",
    )
    create_script.chmod(0o755)

    setup_plan = scripts_dir / "setup-plan.sh"
    setup_plan.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
mkdir -p specs/001-test-feature
plan_file="$(pwd)/specs/001-test-feature/plan.md"
touch "$plan_file"
printf '{"IMPL_PLAN":"%s"}\n' "$plan_file"
""",
        encoding="utf-8",
    )
    setup_plan.chmod(0o755)


def test_start_feature_intake_builds_spec_artifacts_non_interactive(tmp_path: Path) -> None:
    script = _repo_root() / "scripts" / "start_feature_intake.sh"

    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    _write_fake_specify(fake_repo)

    cmd = [
        str(script),
        "-C",
        str(fake_repo),
        "--non-interactive",
        "--json",
        "--title",
        "Add digest filters",
        "--problem",
        "Feed is noisy",
        "--users",
        "Ops team",
        "--in-scope",
        "Filter by source",
        "--out-of-scope",
        "New UI",
        "--acceptance",
        "Can filter by source",
        "--constraints",
        "No DB schema changes",
        "--non-functional",
        "No latency regression",
        "--risks",
        "Filter mismatch",
        "--done",
        "Spec+plan approved and tests green",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"

    spec_dir = fake_repo / "specs" / "001-test-feature"
    assert (spec_dir / "spec-intake.md").exists()
    assert (spec_dir / "execution_packet.md").exists()
    assert (spec_dir / "tasks.md").exists()

    intake_json = Path(payload["intake_json"])
    assert intake_json.exists()
    intake_payload = json.loads(intake_json.read_text(encoding="utf-8"))
    assert intake_payload["title"] == "Add digest filters"


def test_start_feature_intake_requires_title_in_non_interactive_mode(tmp_path: Path) -> None:
    script = _repo_root() / "scripts" / "start_feature_intake.sh"

    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    _write_fake_specify(fake_repo)

    cmd = [
        str(script),
        "-C",
        str(fake_repo),
        "--non-interactive",
        "--problem",
        "Feed is noisy",
        "--users",
        "Ops team",
        "--in-scope",
        "Filter by source",
        "--out-of-scope",
        "New UI",
        "--acceptance",
        "Can filter by source",
        "--constraints",
        "No DB schema changes",
        "--non-functional",
        "No latency regression",
        "--risks",
        "Filter mismatch",
        "--done",
        "Spec+plan approved and tests green",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert result.returncode != 0
    assert "--title is required" in result.stderr
