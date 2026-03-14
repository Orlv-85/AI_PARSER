#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  start_feature_intake.sh [options]

Description:
  Runs feature intake questionnaire, initializes Spec Kit artifacts, and prepares
  an execution packet for multi-agent implementation flow.

Options:
  -C, --repo PATH              Repository path (default: current directory)
  --title TEXT                 Feature title
  --short-name TEXT            Optional short branch suffix for Spec Kit
  --number N                   Optional feature number for Spec Kit
  --problem TEXT               Problem statement
  --users TEXT                 Target users/personas
  --in-scope TEXT              In-scope items
  --out-of-scope TEXT          Out-of-scope items
  --acceptance TEXT            Acceptance criteria
  --constraints TEXT           Constraints and dependencies
  --non-functional TEXT        Non-functional requirements
  --risks TEXT                 Risks and mitigations
  --done TEXT                  Definition of done
  --non-interactive            Fail if any required field is missing
  --json                       Print final output in JSON
  -h, --help                   Show this help

Examples:
  ./scripts/start_feature_intake.sh
  ./scripts/start_feature_intake.sh --non-interactive \
    --title "Add team digest filters" \
    --problem "Digest feed is too noisy" \
    --users "Ops and product team"
USAGE
}

repo="$(pwd)"
title=""
short_name=""
number=""
problem=""
users=""
in_scope=""
out_of_scope=""
acceptance=""
constraints=""
non_functional=""
risks=""
done_def=""
non_interactive=0
json_mode=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -C|--repo)
      repo="${2:-}"
      shift 2
      ;;
    --title)
      title="${2:-}"
      shift 2
      ;;
    --short-name)
      short_name="${2:-}"
      shift 2
      ;;
    --number)
      number="${2:-}"
      shift 2
      ;;
    --problem)
      problem="${2:-}"
      shift 2
      ;;
    --users)
      users="${2:-}"
      shift 2
      ;;
    --in-scope)
      in_scope="${2:-}"
      shift 2
      ;;
    --out-of-scope)
      out_of_scope="${2:-}"
      shift 2
      ;;
    --acceptance)
      acceptance="${2:-}"
      shift 2
      ;;
    --constraints)
      constraints="${2:-}"
      shift 2
      ;;
    --non-functional)
      non_functional="${2:-}"
      shift 2
      ;;
    --risks)
      risks="${2:-}"
      shift 2
      ;;
    --done)
      done_def="${2:-}"
      shift 2
      ;;
    --non-interactive)
      non_interactive=1
      shift
      ;;
    --json)
      json_mode=1
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

if [[ ! -d "$repo" ]]; then
  echo "Error: repo path does not exist: $repo" >&2
  exit 1
fi

prompt_if_empty() {
  local field_name="$1"
  local current_value="$2"
  local prompt_text="$3"

  if [[ -n "$current_value" ]]; then
    printf "%s" "$current_value"
    return 0
  fi

  if [[ "$non_interactive" -eq 1 ]]; then
    echo "Error: --${field_name} is required in --non-interactive mode." >&2
    exit 1
  fi

  local value=""
  read -r -p "$prompt_text" value
  printf "%s" "$value"
}

title="$(prompt_if_empty "title" "$title" "Feature title: ")"
problem="$(prompt_if_empty "problem" "$problem" "Problem statement: ")"
users="$(prompt_if_empty "users" "$users" "Target users/personas: ")"
in_scope="$(prompt_if_empty "in-scope" "$in_scope" "In-scope items: ")"
out_of_scope="$(prompt_if_empty "out-of-scope" "$out_of_scope" "Out-of-scope items: ")"
acceptance="$(prompt_if_empty "acceptance" "$acceptance" "Acceptance criteria: ")"
constraints="$(prompt_if_empty "constraints" "$constraints" "Constraints/dependencies: ")"
non_functional="$(prompt_if_empty "non-functional" "$non_functional" "Non-functional requirements: ")"
risks="$(prompt_if_empty "risks" "$risks" "Risks and mitigations: ")"
done_def="$(prompt_if_empty "done" "$done_def" "Definition of done: ")"

slug="$(python3 - "$title" <<'PY'
import re
import sys
text = sys.argv[1].strip().lower()
text = re.sub(r"[^a-z0-9]+", "-", text)
text = re.sub(r"-+", "-", text).strip("-")
print(text or "feature")
PY
)"

run_id="$(date -u +%Y%m%dT%H%M%SZ)_${slug}_$$"
intake_dir="$repo/tmp/feature_intake/$run_id"
mkdir -p "$intake_dir"

intake_json="$intake_dir/intake.json"
intake_md="$intake_dir/intake.md"

INTAKE_JSON_PATH="$intake_json" \
INTAKE_TITLE="$title" \
INTAKE_PROBLEM="$problem" \
INTAKE_USERS="$users" \
INTAKE_IN_SCOPE="$in_scope" \
INTAKE_OUT_OF_SCOPE="$out_of_scope" \
INTAKE_ACCEPTANCE="$acceptance" \
INTAKE_CONSTRAINTS="$constraints" \
INTAKE_NON_FUNCTIONAL="$non_functional" \
INTAKE_RISKS="$risks" \
INTAKE_DONE="$done_def" \
python3 - <<'PY'
import json
import os
from pathlib import Path

payload = {
    "schema_version": "1.0",
    "title": os.environ["INTAKE_TITLE"],
    "problem": os.environ["INTAKE_PROBLEM"],
    "users": os.environ["INTAKE_USERS"],
    "in_scope": os.environ["INTAKE_IN_SCOPE"],
    "out_of_scope": os.environ["INTAKE_OUT_OF_SCOPE"],
    "acceptance": os.environ["INTAKE_ACCEPTANCE"],
    "constraints": os.environ["INTAKE_CONSTRAINTS"],
    "non_functional": os.environ["INTAKE_NON_FUNCTIONAL"],
    "risks": os.environ["INTAKE_RISKS"],
    "definition_of_done": os.environ["INTAKE_DONE"],
}
Path(os.environ["INTAKE_JSON_PATH"]).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

cat > "$intake_md" <<EOF_MD
# Feature Intake

- Title: $title
- Problem: $problem
- Users: $users
- In scope: $in_scope
- Out of scope: $out_of_scope
- Acceptance: $acceptance
- Constraints: $constraints
- Non-functional: $non_functional
- Risks: $risks
- Definition of done: $done_def
EOF_MD

create_cmd=("$repo/.specify/scripts/bash/create-new-feature.sh" --json)
if [[ -n "$short_name" ]]; then
  create_cmd+=(--short-name "$short_name")
fi
if [[ -n "$number" ]]; then
  create_cmd+=(--number "$number")
fi
create_cmd+=("$title")

create_json="$(cd "$repo" && "${create_cmd[@]}")"

branch_name="$(python3 - "$create_json" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["BRANCH_NAME"])
PY
)"

spec_file="$(python3 - "$create_json" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["SPEC_FILE"])
PY
)"

feature_num="$(python3 - "$create_json" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["FEATURE_NUM"])
PY
)"

plan_json="$(cd "$repo" && .specify/scripts/bash/setup-plan.sh --json)"
plan_file="$(python3 - "$plan_json" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["IMPL_PLAN"])
PY
)"

feature_dir="$(dirname "$spec_file")"
tasks_file="$feature_dir/tasks.md"
if [[ ! -f "$tasks_file" ]] && [[ -f "$repo/.specify/templates/tasks-template.md" ]]; then
  cp "$repo/.specify/templates/tasks-template.md" "$tasks_file"
fi

spec_input_file="$feature_dir/spec-intake.md"
cat > "$spec_input_file" <<EOF_SPEC
# Spec Intake Seed

Use this document as authoritative feature intake input when drafting/updating \

the feature specification.

- Title: $title
- Problem: $problem
- Users: $users
- In scope: $in_scope
- Out of scope: $out_of_scope
- Acceptance: $acceptance
- Constraints: $constraints
- Non-functional: $non_functional
- Risks: $risks
- Definition of done: $done_def

Source artifacts:
- $intake_json
- $intake_md
EOF_SPEC

execution_packet="$feature_dir/execution_packet.md"
cat > "$execution_packet" <<EOF_PACKET
# Multi-Agent Execution Packet

## Feature
- Branch: $branch_name
- Feature #: $feature_num
- Spec: $spec_file
- Plan: $plan_file
- Tasks: $tasks_file
- Intake seed: $spec_input_file

## Required Sequence
1. Update \
   \
   $spec_file using $spec_input_file.
2. Update $plan_file from approved spec.
3. Present spec + plan summary and wait for explicit user approval.
4. Only after approval, run multi-agent implementation via:
   ./scripts/run_multiagent.sh -C $repo -t "TESTER_TASK" -g "GENERATOR_TASK" -r "REVIEWER_TASK"

## Handoff Contract
- tmp/tester_out.json
- tmp/generator_out.json
- tmp/reviewer_out.json

## Suggested Coverage Gate
./scripts/run_multiagent.sh -C $repo -t "TESTER_TASK" -g "GENERATOR_TASK" -r "REVIEWER_TASK" \
  --coverage-cmd "pytest --cov=src/app --cov-report=term-missing" \
  --coverage-fail-under 100

## Readiness Check
./scripts/check_codex_ready.sh -C $repo --timeout-sec 90
EOF_PACKET

run_packet_copy="$intake_dir/execution_packet.md"
cp "$execution_packet" "$run_packet_copy"

if [[ "$json_mode" -eq 1 ]]; then
  RESULT_BRANCH="$branch_name" \
  RESULT_FEATURE_NUM="$feature_num" \
  RESULT_SPEC_FILE="$spec_file" \
  RESULT_PLAN_FILE="$plan_file" \
  RESULT_TASKS_FILE="$tasks_file" \
  RESULT_INTAKE_JSON="$intake_json" \
  RESULT_INTAKE_MD="$intake_md" \
  RESULT_SPEC_INTAKE="$spec_input_file" \
  RESULT_EXEC_PACKET="$execution_packet" \
  python3 - <<'PY'
import json
import os

print(json.dumps({
  "status": "ok",
  "branch": os.environ["RESULT_BRANCH"],
  "feature_num": os.environ["RESULT_FEATURE_NUM"],
  "spec_file": os.environ["RESULT_SPEC_FILE"],
  "plan_file": os.environ["RESULT_PLAN_FILE"],
  "tasks_file": os.environ["RESULT_TASKS_FILE"],
  "intake_json": os.environ["RESULT_INTAKE_JSON"],
  "intake_md": os.environ["RESULT_INTAKE_MD"],
  "spec_intake": os.environ["RESULT_SPEC_INTAKE"],
  "execution_packet": os.environ["RESULT_EXEC_PACKET"],
}, indent=2))
PY
else
  echo "status: ok"
  echo "branch: $branch_name"
  echo "feature_num: $feature_num"
  echo "spec_file: $spec_file"
  echo "plan_file: $plan_file"
  echo "tasks_file: $tasks_file"
  echo "intake_json: $intake_json"
  echo "intake_md: $intake_md"
  echo "spec_intake: $spec_input_file"
  echo "execution_packet: $execution_packet"
fi
