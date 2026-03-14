#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  feature_delivery_flow.sh <command> [options]

Commands:
  bootstrap   Run intake questionnaire + Spec Kit bootstrap and store flow state
  run         Run multi-agent execution for a scoped task (requires explicit approval flag)

Global Options:
  -C, --repo PATH             Repository path (default: current directory)
  --json                      JSON output where applicable
  -h, --help                  Show this help

bootstrap options:
  Any options accepted by scripts/start_feature_intake.sh are forwarded.
  Examples:
    feature_delivery_flow.sh bootstrap
    feature_delivery_flow.sh bootstrap --non-interactive --title "..." --problem "..." ...

run options:
  --feature-dir PATH          Feature directory (e.g. specs/006-my-feature)
  --task TEXT                 Current scoped task/slice description
  --allow TEXT                Allowed file scope description for prompts
  --approved                  Explicit Gate A confirmation (required)
  --sandbox MODE              Sandbox for nested codex (default: workspace-write)
  --retries N                 Retries for wrapper (default: 3)
  --backoff CSV               Backoff list for wrapper (default: 5,10,20)
  --coverage-cmd CMD          Optional coverage command for wrapper gate
  --coverage-fail-under N     Optional coverage threshold

Examples:
  ./scripts/feature_delivery_flow.sh bootstrap

  ./scripts/feature_delivery_flow.sh run \
    --feature-dir specs/006-my-feature \
    --task "Implement endpoint validation errors" \
    --allow "src/app/web,tests/unit" \
    --approved \
    --coverage-cmd "./venv1/bin/pytest --cov=src/app/web --cov-report=term-missing" \
    --coverage-fail-under 100
USAGE
}

repo="$(pwd)"
json_mode=0
start_script=""
multiagent_script=""

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 1
fi

cmd="$1"
shift

# Parse shared global options first (-C/--repo/--json only), keep rest per-command.
rest_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -C|--repo)
      repo="${2:-}"
      shift 2
      ;;
    --json)
      json_mode=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --start-script)
      start_script="${2:-}"
      shift 2
      ;;
    --multiagent-script)
      multiagent_script="${2:-}"
      shift 2
      ;;
    *)
      rest_args+=("$1")
      shift
      ;;
  esac
done

if [[ ! -d "$repo" ]]; then
  echo "Error: repo path does not exist: $repo" >&2
  exit 1
fi

if [[ -z "$start_script" ]]; then
  start_script="$repo/scripts/start_feature_intake.sh"
fi
if [[ -z "$multiagent_script" ]]; then
  multiagent_script="$repo/scripts/run_multiagent.sh"
fi

if [[ ! -x "$start_script" ]]; then
  echo "Error: start script not executable: $start_script" >&2
  exit 1
fi
if [[ ! -x "$multiagent_script" ]]; then
  echo "Error: multiagent script not executable: $multiagent_script" >&2
  exit 1
fi

mkdir -p "$repo/tmp/feature_flow"

run_bootstrap() {
  local forward=()
  if [[ ${#rest_args[@]} -gt 0 ]]; then
    forward=("${rest_args[@]}")
  fi
  local output

  if [[ ${#forward[@]} -gt 0 ]]; then
    output="$(cd "$repo" && "$start_script" -C "$repo" --json "${forward[@]}")"
  else
    output="$(cd "$repo" && "$start_script" -C "$repo" --json)"
  fi

  local branch
  local spec_file
  local plan_file
  local tasks_file
  local execution_packet

  branch="$(python3 - "$output" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["branch"])
PY
)"
  spec_file="$(python3 - "$output" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["spec_file"])
PY
)"
  plan_file="$(python3 - "$output" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["plan_file"])
PY
)"
  tasks_file="$(python3 - "$output" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["tasks_file"])
PY
)"
  execution_packet="$(python3 - "$output" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["execution_packet"])
PY
)"

  local state_file="$repo/tmp/feature_flow/latest_bootstrap.json"
  printf "%s\n" "$output" > "$state_file"
  printf "%s\n" "$output" > "$repo/tmp/feature_flow/${branch}_bootstrap.json"

  if [[ "$json_mode" -eq 1 ]]; then
    printf "%s\n" "$output"
  else
    echo "bootstrap: ok"
    echo "branch: $branch"
    echo "spec: $spec_file"
    echo "plan: $plan_file"
    echo "tasks: $tasks_file"
    echo "execution_packet: $execution_packet"
    echo "state_file: $state_file"
    echo "next: review spec+plan, then run Gate A with --approved in run command"
  fi
}

run_execute() {
  local feature_dir=""
  local task=""
  local allow_scope=""
  local approved=0
  local sandbox="workspace-write"
  local retries="3"
  local backoff="5,10,20"
  local coverage_cmd=""
  local coverage_fail_under=""

  local args=("${rest_args[@]}")
  local i=0
  while [[ $i -lt ${#args[@]} ]]; do
    local key="${args[$i]}"
    case "$key" in
      --feature-dir)
        i=$((i + 1)); feature_dir="${args[$i]:-}"
        ;;
      --task)
        i=$((i + 1)); task="${args[$i]:-}"
        ;;
      --allow)
        i=$((i + 1)); allow_scope="${args[$i]:-}"
        ;;
      --approved)
        approved=1
        ;;
      --sandbox)
        i=$((i + 1)); sandbox="${args[$i]:-}"
        ;;
      --retries)
        i=$((i + 1)); retries="${args[$i]:-}"
        ;;
      --backoff)
        i=$((i + 1)); backoff="${args[$i]:-}"
        ;;
      --coverage-cmd)
        i=$((i + 1)); coverage_cmd="${args[$i]:-}"
        ;;
      --coverage-fail-under)
        i=$((i + 1)); coverage_fail_under="${args[$i]:-}"
        ;;
      *)
        echo "Unknown run option: $key" >&2
        exit 1
        ;;
    esac
    i=$((i + 1))
  done

  if [[ "$approved" -ne 1 ]]; then
    echo "Error: explicit --approved is required (Gate A)." >&2
    exit 1
  fi
  if [[ -z "$feature_dir" || -z "$task" || -z "$allow_scope" ]]; then
    echo "Error: --feature-dir, --task, and --allow are required for run." >&2
    exit 1
  fi

  if [[ "$feature_dir" != /* ]]; then
    feature_dir="$repo/$feature_dir"
  fi

  local spec_file="$feature_dir/spec.md"
  local plan_file="$feature_dir/plan.md"
  local tasks_file="$feature_dir/tasks.md"
  local packet_file="$feature_dir/execution_packet.md"

  for req in "$spec_file" "$plan_file" "$tasks_file" "$packet_file"; do
    if [[ ! -f "$req" ]]; then
      echo "Error: required file not found: $req" >&2
      exit 1
    fi
  done

  local run_id
  run_id="$(date -u +%Y%m%dT%H%M%SZ)_flow_$$"
  local flow_dir="$repo/tmp/feature_flow/$run_id"
  mkdir -p "$flow_dir/prompts"

  local tester_prompt_file="$flow_dir/prompts/tester.txt"
  local generator_prompt_file="$flow_dir/prompts/generator.txt"
  local reviewer_prompt_file="$flow_dir/prompts/reviewer.txt"

  cat > "$tester_prompt_file" <<EOF_TESTER
You are the Tester agent in a spec-first flow.

Read:
- $spec_file
- $plan_file
- $tasks_file
- $packet_file

Task slice:
- $task

Scope restrictions:
- Edit tests only.
- Respect file scope: $allow_scope

Deliverable:
- Write strict JSON handoff to tmp/tester_out.json using schema_version=1.0 and role=tester.
- Include failing_reasons and coverage object keys: command, percent, target_percent, uncovered_lines.
EOF_TESTER

  cat > "$generator_prompt_file" <<EOF_GENERATOR
You are the Generator agent in a spec-first flow.

Read:
- $spec_file
- $plan_file
- $tasks_file
- $packet_file
- tmp/tester_out.json

Task slice:
- $task

Scope restrictions:
- Edit only implementation files in scope: $allow_scope
- Do not edit files outside scope.

Validation before completion:
- Run scoped tests and lint relevant to the slice.

Deliverable:
- Write strict JSON handoff to tmp/generator_out.json using schema_version=1.0 and role=generator.
- Include implementation_notes and coverage object keys: command, percent, target_percent, uncovered_lines.
EOF_GENERATOR

  cat > "$reviewer_prompt_file" <<EOF_REVIEWER
You are the Reviewer agent in a spec-first flow.

Read:
- $spec_file
- $plan_file
- $tasks_file
- $packet_file
- tmp/tester_out.json
- tmp/generator_out.json

Review target:
- $task

Scope:
- Verify only requested slice and allowed scope: $allow_scope

Deliverables:
- Write strict JSON handoff to tmp/reviewer_out.json using schema_version=1.0 and role=reviewer.
- verdict must be PASS or FAIL, include concise reason and requirement checks.
- Write tmp/agent_audit.txt line1=PASS|FAIL, line2=one short reason.
EOF_REVIEWER

  local tester_prompt generator_prompt reviewer_prompt
  tester_prompt="$(cat "$tester_prompt_file")"
  generator_prompt="$(cat "$generator_prompt_file")"
  reviewer_prompt="$(cat "$reviewer_prompt_file")"

  local run_cmd=(
    "$multiagent_script"
    -C "$repo"
    -t "$tester_prompt"
    -g "$generator_prompt"
    -r "$reviewer_prompt"
    --sandbox "$sandbox"
    --retries "$retries"
    --backoff "$backoff"
    --tag "featureflow"
  )

  if [[ -n "$coverage_cmd" ]]; then
    run_cmd+=(--coverage-cmd "$coverage_cmd")
  fi
  if [[ -n "$coverage_fail_under" ]]; then
    run_cmd+=(--coverage-fail-under "$coverage_fail_under")
  fi

  "${run_cmd[@]}"

  local meta_file="$flow_dir/run_meta.json"
  python3 - "$meta_file" "$feature_dir" "$task" "$allow_scope" "$sandbox" "$retries" "$backoff" <<'PY'
import json
import sys

meta_path, feature_dir, task, allow_scope, sandbox, retries, backoff = sys.argv[1:]
payload = {
    "status": "ok",
    "feature_dir": feature_dir,
    "task": task,
    "allow_scope": allow_scope,
    "sandbox": sandbox,
    "retries": int(retries),
    "backoff": backoff,
}
with open(meta_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
print(meta_path)
PY

  if [[ "$json_mode" -eq 1 ]]; then
    cat "$meta_file"
  else
    echo "run: ok"
    echo "feature_dir: $feature_dir"
    echo "task: $task"
    echo "flow_run_dir: $flow_dir"
    echo "next: run final independent checks (pytest/make lint/git diff)"
  fi
}

case "$cmd" in
  bootstrap)
    run_bootstrap
    ;;
  run)
    run_execute
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage >&2
    exit 1
    ;;
esac
