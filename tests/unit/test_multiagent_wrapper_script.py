from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_mock_codex(bin_dir: Path) -> None:
    mock_codex = bin_dir / "codex"
    mock_codex.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

args = sys.argv[1:]
if not args or args[0] != "exec":
    print("unsupported invocation", file=sys.stderr)
    sys.exit(2)

repo = None
output_last = None

idx = 1
while idx < len(args):
    token = args[idx]
    if token == "-C":
        repo = args[idx + 1]
        idx += 2
        continue
    if token == "--sandbox":
        idx += 2
        continue
    if token == "--output-last-message":
        output_last = args[idx + 1]
        idx += 2
        continue
    # last positional prompt
    idx += 1

if not repo:
    print("missing repo", file=sys.stderr)
    sys.exit(3)

repo_path = pathlib.Path(repo)
repo_path.joinpath("tmp").mkdir(parents=True, exist_ok=True)

role = "reviewer"
if output_last and "tester" in output_last:
    role = "tester"
elif output_last and "generator" in output_last:
    role = "generator"

if output_last:
    repo_path.joinpath(output_last).write_text(f"{role} done\\n", encoding="utf-8")

common = {
    "schema_version": "1.0",
    "role": role,
    "status": "PASS",
    "summary": f"{role} ok",
    "changed_files": [],
    "checks": ["mock:pass"],
    "artifacts": [],
    "next_action": "next",
}

if role == "tester":
    payload = {
        **common,
        "failing_reasons": [],
        "coverage": {
            "command": "mock",
            "percent": 100,
            "target_percent": 100,
            "uncovered_lines": [],
        },
    }
    repo_path.joinpath("tmp/tester_out.json").write_text(json.dumps(payload), encoding="utf-8")
elif role == "generator":
    payload = {
        **common,
        "implementation_notes": ["mock"],
        "coverage": {
            "command": "mock",
            "percent": 100,
            "target_percent": 100,
            "uncovered_lines": [],
        },
    }
    repo_path.joinpath("tmp/generator_out.json").write_text(json.dumps(payload), encoding="utf-8")
else:
    payload = {
        **common,
        "verdict": "PASS",
        "reason": "mock pass",
        "requirements": ["R1=PASS"],
    }
    repo_path.joinpath("tmp/reviewer_out.json").write_text(json.dumps(payload), encoding="utf-8")
    repo_path.joinpath("tmp/agent_audit.txt").write_text("PASS\\nmock pass\\n", encoding="utf-8")

sys.exit(0)
""",
        encoding="utf-8",
    )
    mock_codex.chmod(0o755)


def _run_wrapper(tmp_path: Path, extra_args: list[str]) -> subprocess.CompletedProcess[str]:
    repo_root = _repo_root()
    wrapper = repo_root / "scripts" / "run_multiagent.sh"

    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    (fake_repo / "tmp").mkdir()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_mock_codex(fake_bin)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    cmd = [
        str(wrapper),
        "-C",
        str(fake_repo),
        "-t",
        "tester",
        "-g",
        "generator",
        "-r",
        "reviewer",
        "--retries",
        "1",
        "--backoff",
        "0",
        *extra_args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)


def test_wrapper_passes_with_coverage_gate_and_writes_run_archive(tmp_path: Path) -> None:
    result = _run_wrapper(
        tmp_path,
        [
            "--coverage-cmd",
            "printf 'TOTAL 10 0 100%%\\n'",
            "--coverage-fail-under",
            "95",
        ],
    )

    assert result.returncode == 0, result.stderr

    fake_repo = tmp_path / "fake_repo"
    latest_link = fake_repo / "tmp" / "runs" / "latest"
    assert latest_link.exists()

    run_dir = latest_link.resolve()
    assert (run_dir / "handoffs" / "tester.json").exists()
    assert (run_dir / "handoffs" / "generator.json").exists()
    assert (run_dir / "handoffs" / "reviewer.json").exists()
    assert (run_dir / "handoffs" / "coverage_gate.json").exists()

    coverage_gate = json.loads((run_dir / "handoffs" / "coverage_gate.json").read_text())
    assert coverage_gate["status"] == "PASS"
    assert float(coverage_gate["percent"]) >= 95


def test_wrapper_fails_when_coverage_is_below_threshold(tmp_path: Path) -> None:
    result = _run_wrapper(
        tmp_path,
        [
            "--coverage-cmd",
            "printf 'TOTAL 10 2 80%%\\n'",
            "--coverage-fail-under",
            "90",
        ],
    )

    assert result.returncode != 0
    assert "[coverage] failed" in result.stderr

    fake_repo = tmp_path / "fake_repo"
    assert not (fake_repo / "tmp" / "reviewer_out.json").exists()
