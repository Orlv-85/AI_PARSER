---
name: multi-agent-orchestration
description: Use when user asks to run codex inside codex (nested agents), split work between executor/reviewer, or orchestrate parallel subtasks via `codex exec` from terminal.
---

# Multi-Agent Orchestration (Nested Codex)

Use this skill when the user asks for multi-agent work, for example: "запусти другого агента", "executor/reviewer", "codex внутри codex", or "разбей на подзадачи".

## Goal

Run isolated sub-agents through `codex exec`, then verify outputs from the orchestrator.

Default pattern:
1. Executor creates or changes artifacts.
2. Reviewer validates and writes an audit artifact.
3. Orchestrator performs final independent checks (diff/tests/lint).

## Preconditions

- Run from repository root.
- Prefer sandboxed execution: `--sandbox workspace-write`.
- Constrain scope to dedicated paths (`tmp/...` or explicit target files).

## Standard Workflow

### 1) Prepare task boundary

- Define exact files the executor may modify.
- Define validation criteria for reviewer (PASS/FAIL + short reason).
- Avoid prompts like "fix everything" without scope.

### 2) Run Executor

```bash
/bin/zsh -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "TASK_FOR_EXECUTOR. Modify only ALLOWED_PATHS."'
```

Executor prompt template:

```text
Implement TASK_X.
Constraints:
- Modify only: PATH_A, PATH_B
- Do not touch any other files
- If blocked, write short blocker note to tmp/agent_blocker.txt
Output:
- Apply changes directly
```

### 3) Run Reviewer

```bash
/bin/zsh -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "Validate RESULTS against REQUIREMENTS. Write tmp/agent_audit.txt with PASS or FAIL on line 1 and one short reason on line 2. Do not modify files outside tmp/."'
```

Reviewer prompt template:

```text
Review executor changes for TASK_X.
Validation:
- Requirement 1
- Requirement 2
Output file:
- tmp/agent_audit.txt
Format:
- Line 1: PASS or FAIL
- Line 2: one short reason
Restrictions:
- Do not modify source files
- Only write tmp/agent_audit.txt
```

### 4) Orchestrator final checks (mandatory)

Run independent checks, not just reviewer output:

```bash
git diff -- PATH_A PATH_B
pytest -q
make lint
cat tmp/agent_audit.txt
```

Choose only relevant checks for the task. If checks fail, either:
- re-run executor with focused fix prompt, or
- fix directly in orchestrator if faster and safer.

## Reusable Command Blocks

### Minimal single nested run

```bash
codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "YOUR_TASK_PROMPT"
```

### Executor + Reviewer pair

```bash
/bin/zsh -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "EXECUTOR_TASK"'
/bin/zsh -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "REVIEWER_TASK"'
```

## Reliability Rules

- If `stdin is not a terminal`, use `codex exec` (not interactive `codex`).
- If `401 Unauthorized`, run `codex login` in the same environment/profile.
- On transient API/network errors, retry the same command once or twice.
- Keep prompts deterministic: exact output paths, exact format, explicit restrictions.

## Safety Rules

- Never allow unrestricted edits when scope can be narrowed.
- For critical tasks always include reviewer step.
- Never skip final orchestrator verification.

## Done Criteria

Consider multi-agent task complete only when all are true:
1. Executor artifact exists and matches task scope.
2. Reviewer produced audit with expected format.
3. Orchestrator checks passed (tests/lint/diff as applicable).
4. No out-of-scope files changed.

## Script Helper

Use bundled wrapper when you want one command for executor+reviewer:

```bash
~/.codex/skills/multi-agent-orchestration/scripts/run_executor_reviewer.sh \
  -C /ABS/PATH/TO/REPO \
  -e "EXECUTOR_TASK" \
  -r "REVIEWER_TASK"
```

Notes:
- Script runs executor first, then reviewer.
- Default sandbox is `workspace-write` (override with `--sandbox`).
- If reviewer writes `tmp/agent_audit.txt`, script prints it.
- Orchestrator checks (`pytest`, `make lint`, `git diff`) are still mandatory.
