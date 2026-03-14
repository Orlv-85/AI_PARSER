from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_check_codex_ready_script_passes_with_mock_codex(tmp_path: Path) -> None:
    script = _repo_root() / "scripts" / "check_codex_ready.sh"

    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    (fake_repo / "tmp").mkdir()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    mock_codex = fake_bin / "codex"
    mock_codex.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

args = sys.argv[1:]
repo = None
last = None
prompt = ""
idx = 0
while idx < len(args):
    token = args[idx]
    if token == "-C":
        repo = args[idx + 1]
        idx += 2
        continue
    if token == "--output-last-message":
        last = args[idx + 1]
        idx += 2
        continue
    if token == "--sandbox":
        idx += 2
        continue
    prompt = args[idx]
    idx += 1

if not repo:
    raise SystemExit(2)

repo_path = pathlib.Path(repo)
probe = repo_path / "tmp" / "codex_ready_probe.json"
probe.write_text(json.dumps({"ok": True, "source": "codex-ready-probe"}), encoding="utf-8")
if last:
    (repo_path / last).write_text("ok\\n", encoding="utf-8")
_ = prompt
raise SystemExit(0)
""",
        encoding="utf-8",
    )
    mock_codex.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    result = subprocess.run(
        [str(script), "-C", str(fake_repo), "--timeout-sec", "10"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "codex ready probe: PASS" in result.stdout
    assert (fake_repo / "tmp" / "codex_ready_probe.json").exists()
