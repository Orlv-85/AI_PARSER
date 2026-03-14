#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  check_codex_ready.sh [-C /ABS/PATH/TO/REPO] [--sandbox workspace-write] [--timeout-sec 90]

Description:
  Runs a minimal live codex exec probe and verifies artifact write in tmp/.

Options:
  -C, --repo         Repo path (default: current directory)
  --sandbox          Codex sandbox mode (default: workspace-write)
  --timeout-sec N    Probe timeout in seconds (default: 90)
  -h, --help         Show this help
USAGE
}

repo="$(pwd)"
sandbox="workspace-write"
timeout_sec="90"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -C|--repo)
      repo="${2:-}"
      shift 2
      ;;
    --sandbox)
      sandbox="${2:-}"
      shift 2
      ;;
    --timeout-sec)
      timeout_sec="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$repo" ]]; then
  echo "Error: repo path does not exist: $repo" >&2
  exit 1
fi

if ! [[ "$timeout_sec" =~ ^[0-9]+$ ]] || [[ "$timeout_sec" -lt 5 ]]; then
  echo "Error: --timeout-sec must be integer >= 5" >&2
  exit 1
fi

mkdir -p "$repo/tmp"
probe_json_rel="tmp/codex_ready_probe.json"
probe_last_rel="tmp/codex_ready_last.md"
probe_log_abs="$repo/tmp/codex_ready_probe.log"
probe_json_abs="$repo/$probe_json_rel"

rm -f "$probe_json_abs"

prompt="Write exactly one JSON file at ${probe_json_rel} with: {\"ok\": true, \"source\": \"codex-ready-probe\"}. Do not modify any other files."

python3 - "$repo" "$sandbox" "$probe_last_rel" "$prompt" "$timeout_sec" "$probe_log_abs" <<'PY'
import pathlib
import subprocess
import sys

repo, sandbox, last_rel, prompt, timeout_sec, log_path = sys.argv[1:]
cmd = ["codex", "exec", "-C", repo, "--sandbox", sandbox, "--output-last-message", last_rel, prompt]

try:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=int(timeout_sec),
        check=False,
    )
except subprocess.TimeoutExpired:
    pathlib.Path(log_path).write_text("probe timeout\n", encoding="utf-8")
    print("probe timeout", file=sys.stderr)
    raise SystemExit(1)

pathlib.Path(log_path).write_text(proc.stdout or "", encoding="utf-8")
if proc.returncode != 0:
    print(f"probe failed: codex exit {proc.returncode}", file=sys.stderr)
    raise SystemExit(proc.returncode)
PY

python3 - "$probe_json_abs" <<'PY'
import json
import pathlib
import sys

probe_path = pathlib.Path(sys.argv[1])
if not probe_path.exists():
    print(f"probe failed: missing {probe_path}", file=sys.stderr)
    raise SystemExit(1)

try:
    data = json.loads(probe_path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"probe failed: invalid json: {exc}", file=sys.stderr)
    raise SystemExit(1)

if data.get("ok") is not True:
    print("probe failed: json.ok != true", file=sys.stderr)
    raise SystemExit(1)

print("codex ready probe: PASS")
PY

echo "Probe artifacts: $probe_json_rel, $probe_last_rel, tmp/codex_ready_probe.log"
