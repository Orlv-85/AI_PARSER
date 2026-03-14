#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  run_executor_reviewer.sh -C /ABS/PATH/TO/REPO -t "TESTER_TASK" -g "GENERATOR_TASK" -r "REVIEWER_TASK" [options]
  run_executor_reviewer.sh -C /ABS/PATH/TO/REPO -e "EXECUTOR_TASK" -r "REVIEWER_TASK" [options]

Description:
  Runs nested Codex agents sequentially with retries and stable shell defaults.
  Primary pattern: tester -> generator -> reviewer.
  Legacy mode: executor -> reviewer (using -e and -r).

Options:
  -C, --repo            Absolute path to repository
  -t, --tester          Tester task prompt
  -g, --generator       Generator task prompt
  -r, --reviewer        Reviewer task prompt
  -e, --executor        Legacy alias for generator prompt
  --sandbox             Codex sandbox mode (default: workspace-write)
  --retries N           Retry attempts per agent (default: 3)
  --backoff SEC_LIST    Comma-separated backoff seconds (default: 5,10,20)
  --tag NAME            Prefix for tmp artifacts (default: multiagent)
  --tester-handoff P    Expected tester handoff file (default: tmp/tester_out.json)
  --generator-handoff P Expected generator handoff file (default: tmp/generator_out.json)
  --reviewer-handoff P  Expected reviewer handoff file (default: tmp/reviewer_out.json)
  --runs-dir P          Relative runs directory (default: tmp/runs)
  --stream-logs         Stream nested codex output to stdout while saving logs
  --coverage-cmd CMD    Coverage command executed after generator step
  --coverage-fail-under N  Minimum coverage percent required (0..100)
  --coverage-log P      Coverage log path relative to repo (default: tmp/coverage_gate.log)
  --no-json-validate    Disable strict JSON handoff validation
  -h, --help            Show this help
USAGE
}

repo=""
tester_task=""
generator_task=""
reviewer_task=""
sandbox="workspace-write"
retries=3
backoff_csv="5,10,20"
tag="multiagent"
tester_handoff="tmp/tester_out.json"
generator_handoff="tmp/generator_out.json"
reviewer_handoff="tmp/reviewer_out.json"
runs_dir_rel="tmp/runs"
coverage_cmd=""
coverage_fail_under=""
coverage_log_rel="tmp/coverage_gate.log"
json_validate=1
stream_logs=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -C|--repo)
      repo="${2:-}"
      shift 2
      ;;
    -t|--tester)
      tester_task="${2:-}"
      shift 2
      ;;
    -g|--generator)
      generator_task="${2:-}"
      shift 2
      ;;
    -e|--executor)
      generator_task="${2:-}"
      shift 2
      ;;
    -r|--reviewer)
      reviewer_task="${2:-}"
      shift 2
      ;;
    --sandbox)
      sandbox="${2:-}"
      shift 2
      ;;
    --retries)
      retries="${2:-}"
      shift 2
      ;;
    --backoff)
      backoff_csv="${2:-}"
      shift 2
      ;;
    --tag)
      tag="${2:-}"
      shift 2
      ;;
    --tester-handoff)
      tester_handoff="${2:-}"
      shift 2
      ;;
    --generator-handoff)
      generator_handoff="${2:-}"
      shift 2
      ;;
    --reviewer-handoff)
      reviewer_handoff="${2:-}"
      shift 2
      ;;
    --runs-dir)
      runs_dir_rel="${2:-}"
      shift 2
      ;;
    --stream-logs)
      stream_logs=1
      shift
      ;;
    --coverage-cmd)
      coverage_cmd="${2:-}"
      shift 2
      ;;
    --coverage-fail-under)
      coverage_fail_under="${2:-}"
      shift 2
      ;;
    --coverage-log)
      coverage_log_rel="${2:-}"
      shift 2
      ;;
    --no-json-validate)
      json_validate=0
      shift
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

if [[ -z "$repo" || -z "$reviewer_task" ]]; then
  echo "Error: --repo and --reviewer are required." >&2
  usage >&2
  exit 1
fi

if [[ -z "$tester_task" && -z "$generator_task" ]]; then
  echo "Error: provide either tester+generator (-t and -g) or legacy executor (-e)." >&2
  usage >&2
  exit 1
fi

if [[ ! -d "$repo" ]]; then
  echo "Error: repo path does not exist: $repo" >&2
  exit 1
fi

if ! [[ "$retries" =~ ^[0-9]+$ ]] || [[ "$retries" -lt 1 ]]; then
  echo "Error: --retries must be an integer >= 1" >&2
  exit 1
fi

if [[ -n "$coverage_fail_under" ]]; then
  if ! [[ "$coverage_fail_under" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "Error: --coverage-fail-under must be a number in [0,100]." >&2
    exit 1
  fi
  if ! python3 - "$coverage_fail_under" <<'PY'
import sys
v = float(sys.argv[1])
if v < 0 or v > 100:
    raise SystemExit(1)
PY
  then
    echo "Error: --coverage-fail-under must be in [0,100]." >&2
    exit 1
  fi
fi

if [[ -n "$coverage_fail_under" && -z "$coverage_cmd" ]]; then
  echo "Error: --coverage-fail-under requires --coverage-cmd." >&2
  exit 1
fi

if [[ "$json_validate" -eq 1 ]] && ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required for strict JSON validation." >&2
  exit 1
fi

mkdir -p "$repo/tmp" "$repo/$runs_dir_rel"

run_id="$(date -u +%Y%m%dT%H%M%SZ)_${tag}_$$"
run_dir="$repo/$runs_dir_rel/$run_id"
mkdir -p "$run_dir/prompts" "$run_dir/logs" "$run_dir/handoffs" "$run_dir/messages"

# Stable pointer to latest run for quick inspection.
ln -sfn "$run_dir" "$repo/$runs_dir_rel/latest"

IFS=',' read -r -a backoff_values <<< "$backoff_csv"

shell_bin=""
shell_args=()
if command -v zsh >/dev/null 2>&1; then
  shell_bin="$(command -v zsh)"
  shell_args=(-f -lc)
elif command -v bash >/dev/null 2>&1; then
  shell_bin="$(command -v bash)"
  shell_args=(-lc)
else
  shell_bin="$(command -v sh)"
  shell_args=(-lc)
fi

validate_json_handoff() {
  local role="$1"
  local handoff_abs="$2"

  python3 - "$role" "$handoff_abs" <<'PY'
import json
import pathlib
import sys

role = sys.argv[1]
path = pathlib.Path(sys.argv[2])

if not path.exists() or path.stat().st_size == 0:
    print(f"missing_or_empty_handoff:{path}", file=sys.stderr)
    sys.exit(1)

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"invalid_json:{path}:{exc}", file=sys.stderr)
    sys.exit(1)

if not isinstance(data, dict):
    print("schema_error:root must be object", file=sys.stderr)
    sys.exit(1)

base_required = {
    "schema_version": str,
    "role": str,
    "status": str,
    "summary": str,
    "changed_files": list,
    "checks": list,
    "artifacts": list,
    "next_action": str,
}

role_required = {
    "tester": {
        "failing_reasons": list,
        "coverage": dict,
    },
    "generator": {
        "implementation_notes": list,
        "coverage": dict,
    },
    "reviewer": {
        "verdict": str,
        "reason": str,
        "requirements": list,
    },
}

if role not in role_required:
    print(f"schema_error:unsupported_role:{role}", file=sys.stderr)
    sys.exit(1)

required = dict(base_required)
required.update(role_required[role])

allowed_keys = set(required.keys())
actual_keys = set(data.keys())
missing = sorted(allowed_keys - actual_keys)
extra = sorted(actual_keys - allowed_keys)

if missing:
    print("schema_error:missing_keys:" + ",".join(missing), file=sys.stderr)
    sys.exit(1)
if extra:
    print("schema_error:extra_keys:" + ",".join(extra), file=sys.stderr)
    sys.exit(1)

for key, expected_type in required.items():
    if not isinstance(data[key], expected_type):
        print(f"schema_error:type:{key}:expected={expected_type.__name__}", file=sys.stderr)
        sys.exit(1)

if data["role"] != role:
    print(f"schema_error:role_mismatch:expected={role}:actual={data['role']}", file=sys.stderr)
    sys.exit(1)

if data["schema_version"] != "1.0":
    print("schema_error:schema_version must be 1.0", file=sys.stderr)
    sys.exit(1)

status = str(data["status"]).strip().upper()
allowed_status = {"PASS", "FAIL", "NEEDS_WORK"}
status_aliases = {
    "OK": "PASS",
    "DONE": "PASS",
    "COMPLETED": "PASS",
    "SUCCESS": "PASS",
    "BLOCKED": "NEEDS_WORK",
}
status = status_aliases.get(status, status)
if status not in allowed_status:
    print(
        f"schema_warn:unknown status '{data['status']}', normalized to NEEDS_WORK",
        file=sys.stderr,
    )
    status = "NEEDS_WORK"
data["status"] = status

if role in {"tester", "generator"}:
    cov = data["coverage"]
    cov_required = {
        "command": str,
        "percent": (int, float),
        "target_percent": (int, float),
        "uncovered_lines": list,
    }
    if set(cov.keys()) != set(cov_required.keys()):
        print("schema_error:coverage keys mismatch", file=sys.stderr)
        sys.exit(1)
    for ck, ctype in cov_required.items():
        if not isinstance(cov[ck], ctype):
            typename = ctype.__name__ if isinstance(ctype, type) else "number"
            print(f"schema_error:coverage.{ck}:expected={typename}", file=sys.stderr)
            sys.exit(1)

if role == "reviewer":
    verdict = str(data["verdict"]).strip().upper()
    verdict_aliases = {"OK": "PASS", "SUCCESS": "PASS", "BLOCKER": "FAIL", "BLOCKED": "FAIL"}
    verdict = verdict_aliases.get(verdict, verdict)
    if verdict not in {"PASS", "FAIL"}:
        print("schema_error:reviewer.verdict must be PASS|FAIL", file=sys.stderr)
        sys.exit(1)
    data["verdict"] = verdict

# Persist normalized fields so downstream steps see canonical values.
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print("ok")
PY
}

extract_coverage_percent() {
  local log_abs="$1"
  python3 - "$log_abs" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
# Prefer coverage TOTAL line when present.
total_hits = re.findall(r"^TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%", text, flags=re.MULTILINE)
if total_hits:
    print(total_hits[-1])
    raise SystemExit(0)

# Fallback to the last percentage in log.
all_hits = re.findall(r"(\d+(?:\.\d+)?)%", text)
if all_hits:
    print(all_hits[-1])
PY
}

run_coverage_gate() {
  local log_abs="$repo/$coverage_log_rel"
  local run_log_abs="$run_dir/logs/coverage.log"

  echo "[coverage] running coverage gate..."
  set +e
  "$shell_bin" "${shell_args[@]}" "cd '$repo' && $coverage_cmd" >"$log_abs" 2>&1
  local rc=$?
  set -e

  cp "$log_abs" "$run_log_abs"

  local coverage_percent=""
  if [[ -n "$coverage_fail_under" ]]; then
    coverage_percent="$(extract_coverage_percent "$log_abs" | tr -d '[:space:]')"
    if [[ -z "$coverage_percent" ]]; then
      echo "[coverage] failed: could not parse coverage percent from log ($log_abs)" >&2
      return 1
    fi

    if ! python3 - "$coverage_percent" "$coverage_fail_under" <<'PY'
import sys
actual = float(sys.argv[1])
required = float(sys.argv[2])
if actual < required:
    raise SystemExit(1)
PY
    then
      echo "[coverage] failed: ${coverage_percent}% < required ${coverage_fail_under}%" >&2
      return 1
    fi
  fi

  if [[ "$rc" -ne 0 ]]; then
    echo "[coverage] failed: coverage command exited with code $rc" >&2
    return 1
  fi

  cat > "$run_dir/handoffs/coverage_gate.json" <<JSON
{
  "command": $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$coverage_cmd"),
  "log": $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$coverage_log_rel"),
  "percent": ${coverage_percent:-null},
  "required_percent": ${coverage_fail_under:-null},
  "status": "PASS"
}
JSON

  echo "[coverage] gate passed"
}

run_agent() {
  local role="$1"
  local prompt="$2"
  local handoff_rel="$3"
  local message_rel="tmp/${tag}_${role}_last.md"
  local prompt_abs="$run_dir/prompts/${role}.txt"
  local handoff_abs="$repo/$handoff_rel"
  local message_abs="$repo/$message_rel"
  local log_abs="$repo/tmp/${tag}_${role}.log"
  local run_log_abs="$run_dir/logs/${role}.log"

  printf "%s\n" "$prompt" > "$prompt_abs"

  local attempt=1
  while [[ "$attempt" -le "$retries" ]]; do
    echo "[${role}] attempt ${attempt}/${retries}"
    set +e
    local rc=0
    if [[ "$stream_logs" -eq 1 ]]; then
      "$shell_bin" "${shell_args[@]}" "codex exec -C '$repo' --sandbox '$sandbox' --output-last-message '$message_rel' \"\$(cat '$prompt_abs')\"" \
        2>&1 | tee "$log_abs"
      rc=${PIPESTATUS[0]}
    else
      "$shell_bin" "${shell_args[@]}" "codex exec -C '$repo' --sandbox '$sandbox' --output-last-message '$message_rel' \"\$(cat '$prompt_abs')\"" \
        >"$log_abs" 2>&1
      rc=$?
    fi
    set -e

    cp "$log_abs" "$run_log_abs"

    if [[ "$rc" -eq 0 ]]; then
      echo "[${role}] exit code 0"
    else
      # Nested codex may still produce artifacts despite transport errors.
      if [[ -s "$handoff_abs" || -s "$message_abs" ]]; then
        echo "[${role}] non-zero exit but artifact exists; continuing."
      else
        if [[ "$attempt" -lt "$retries" ]]; then
          local idx=$((attempt - 1))
          local sleep_sec=5
          if [[ "$idx" -lt "${#backoff_values[@]}" && -n "${backoff_values[$idx]}" ]]; then
            sleep_sec="${backoff_values[$idx]}"
          fi
          echo "[${role}] retrying in ${sleep_sec}s"
          sleep "$sleep_sec"
          attempt=$((attempt + 1))
          continue
        fi
        echo "[${role}] failed after ${retries} attempts. Log: $log_abs" >&2
        return 1
      fi
    fi

    if [[ -s "$message_abs" ]]; then
      cp "$message_abs" "$run_dir/messages/${role}_last.md"
    fi

    if [[ -s "$handoff_abs" ]]; then
      cp "$handoff_abs" "$run_dir/handoffs/${role}.json"
    else
      echo "[${role}] expected handoff missing: $handoff_abs" >&2
      return 1
    fi

    if [[ "$json_validate" -eq 1 ]]; then
      echo "[${role}] validating JSON handoff schema..."
      validate_json_handoff "$role" "$handoff_abs" > /dev/null
      echo "[${role}] JSON handoff valid"
    fi

    return 0
  done

  echo "[${role}] failed after ${retries} attempts. Log: $log_abs" >&2
  return 1
}

if [[ -n "$tester_task" ]]; then
  echo "[1/3] Running tester..."
  run_agent "tester" "$tester_task" "$tester_handoff"
else
  echo "[1/2] Tester step skipped (legacy mode)."
fi

echo "[2/3] Running generator/executor..."
run_agent "generator" "$generator_task" "$generator_handoff"

if [[ -n "$coverage_cmd" ]]; then
  run_coverage_gate
fi

echo "[3/3] Running reviewer..."
run_agent "reviewer" "$reviewer_task" "$reviewer_handoff"

cat > "$run_dir/manifest.txt" <<MANIFEST
run_id=$run_id
repo=$repo
sandbox=$sandbox
tester_handoff=$tester_handoff
generator_handoff=$generator_handoff
reviewer_handoff=$reviewer_handoff
json_validate=$json_validate
coverage_cmd=$coverage_cmd
coverage_fail_under=$coverage_fail_under
coverage_log=$coverage_log_rel
MANIFEST

echo ""
echo "Run archive: $run_dir"
if [[ -f "$repo/$reviewer_handoff" ]]; then
  echo "Reviewer handoff ($reviewer_handoff):"
  cat "$repo/$reviewer_handoff"
else
  echo "Reviewer finished. Handoff file not found at: $repo/$reviewer_handoff"
fi

echo ""
echo "Next: run independent checks (e.g. pytest, make lint, git diff)."
