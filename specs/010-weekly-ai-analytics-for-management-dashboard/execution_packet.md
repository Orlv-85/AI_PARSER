# Multi-Agent Execution Packet

## Feature
- Branch: 010-weekly-ai-analytics-for-management-dashboard
- Feature #: 010
- Spec: /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/010-weekly-ai-analytics-for-management-dashboard/spec.md
- Plan: /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/010-weekly-ai-analytics-for-management-dashboard/plan.md
- Tasks: /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/010-weekly-ai-analytics-for-management-dashboard/tasks.md
- Intake seed: /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/010-weekly-ai-analytics-for-management-dashboard/spec-intake.md

## Required Sequence
1. Update       /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/010-weekly-ai-analytics-for-management-dashboard/spec.md using /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/010-weekly-ai-analytics-for-management-dashboard/spec-intake.md.
2. Update /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/010-weekly-ai-analytics-for-management-dashboard/plan.md from approved spec.
3. Present spec + plan summary and wait for explicit user approval.
4. Only after approval, run multi-agent implementation via:
   ./scripts/run_multiagent.sh -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER -t "TESTER_TASK" -g "GENERATOR_TASK" -r "REVIEWER_TASK"

## Handoff Contract
- tmp/tester_out.json
- tmp/generator_out.json
- tmp/reviewer_out.json

## Suggested Coverage Gate
./scripts/run_multiagent.sh -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER -t "TESTER_TASK" -g "GENERATOR_TASK" -r "REVIEWER_TASK"   --coverage-cmd "pytest --cov=src/app --cov-report=term-missing"   --coverage-fail-under 100

## Readiness Check
./scripts/check_codex_ready.sh -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER --timeout-sec 90
