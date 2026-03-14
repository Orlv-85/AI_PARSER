---
name: multi-agent-orchestration
description: Use when user asks to run codex inside codex (nested agents), especially with tester/generator/reviewer TDD flow, executor/reviewer validation, or parallel subtasks via `codex exec` from terminal.
---

# Multi-Agent Orchestration (Nested Codex)

Use this skill when the user asks for multi-agent work, for example: "запусти другого агента", "tester/generator/reviewer", "executor/reviewer", "codex внутри codex", or "разбей на подзадачи".

## Goal

Run isolated sub-agents through `codex exec`, then verify outputs from the orchestrator.

Default pattern:
1. Tester writes tests only.
2. Generator writes code and runs tests/lint.
3. Tester strengthens tests (edge cases + coverage closure).
4. Generator adapts code until strengthened tests stay green.
5. Reviewer validates and writes an audit artifact.
6. Orchestrator performs final independent checks (diff/tests/lint/coverage).

## Preconditions

- Run from repository root.
- Prefer sandboxed execution: `--sandbox workspace-write`.
- Constrain scope to dedicated paths (`tmp/...` or explicit target files).
- Use `tmp/` as shared handoff area between agents.

## Standard Workflow

### 1) Prepare task boundary

- Define exact files each agent may modify.
- Define validation criteria for reviewer (PASS/FAIL + short reason).
- Define handoff files in `tmp/`:
  - `tmp/tester_out.json`
  - `tmp/generator_out.json`
  - `tmp/reviewer_out.json`
- Define a scoped coverage target up front (default: `100%` for touched files / target modules in this task).
- Define the exact coverage command and report format to avoid ambiguity.
- Avoid prompts like "fix everything" without scope.

### 2) Run Tester

```bash
/bin/zsh -f -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "TESTER_TASK. Modify only tests and write tmp/tester_out.json."'
```

Tester responsibilities (explicit):
- Start with failing tests for the requested behavior.
- After generator reaches green once, add strengthening tests for edge cases and regressions.
- Drive coverage to the agreed scoped target (default `100%`).
- Write in `tmp/tester_out.json`:
  - tests added,
  - current failing reason(s),
  - coverage command,
  - current scoped coverage % and uncovered lines.

### 3) Run Generator

```text
Implement TASK_X.
Constraints:
- Modify only: source files in allowed scope
- Do not touch any other files
- Run test command and make lint before finishing
- Run full repository test suite (`pytest`) before finishing, unless user explicitly approves scoped-only testing
- Run the scoped coverage command before finishing
- Write handoff summary to tmp/generator_out.json
Output:
- Apply changes directly
```

Generator completion rule (important):
- Do **not** consider the task done after the first green test run.
- If tests are green but scoped coverage is below target, hand back to Tester for strengthening tests.
- After Tester strengthens tests, rerun implementation loop until:
  - tests are green,
  - full test suite is green (or an explicit user-approved exception exists),
  - lint passes (or clearly documented pre-existing unrelated failures),
  - scoped coverage meets target.

Recommended generator handoff fields in `tmp/generator_out.json`:
- full test suite command + result
- test command + result
- lint command + result
- coverage command + result
- explicit note whether coverage target is met
- any unrelated/pre-existing failures outside scope

### 3.5) Strengthening Trigger (Tester <-> Generator)

Return to Tester for strengthening when any of the following is true:
- First green run has been reached for the scoped tests.
- Coverage is below the scoped target.
- New logic branches/conditions were introduced without direct assertions.
- Bug fix was implemented without a regression test reproducing the prior failure.

Return to Generator after Tester updates tests and records:
- what edge cases were added,
- what lines/branches were previously uncovered,
- the new expected failing behavior (if any).

### 4) Run Reviewer

```bash
/bin/zsh -f -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "Validate RESULTS against REQUIREMENTS. Write tmp/reviewer_out.json and tmp/agent_audit.txt with PASS or FAIL on line 1 and one short reason on line 2. Do not modify files outside tmp/."'
```

Reviewer prompt template:

```text
Review executor changes for TASK_X.
Validation:
- Requirement 1
- Requirement 2
Output file:
- tmp/reviewer_out.json
- tmp/agent_audit.txt
Format:
- Line 1: PASS or FAIL
- Line 2: one short reason
Restrictions:
- Do not modify source files
- Only write files inside tmp/
```

### 5) Orchestrator final checks (mandatory)

Run independent checks, not just reviewer output:

```bash
git diff -- PATH_A PATH_B
pytest -q
make lint
pytest --cov=MODULE_OR_PATH --cov-report=term-missing --cov-fail-under=100
cat tmp/agent_audit.txt
```

Choose only relevant checks for the task. If checks fail, either:
- re-run tester/generator with focused fix prompt, or
- fix directly in orchestrator if faster and safer.

Coverage policy (default):
- Treat `100%` as a **scoped** requirement unless the user explicitly says repo-wide.
- Scope must be declared before implementation (examples):
  - changed files only,
  - target package/module for the task,
  - specific endpoint/service file(s).
- If `100%` is not realistically enforceable (generated code, framework glue, unreachable guards), require explicit exception list in tester/reviewer handoff with justification.

## Reusable Command Blocks

### Feature Intake + Spec Kit Bootstrap

Use this before new feature delivery when scope is still raw and you want deterministic intake artifacts:

```bash
./scripts/start_feature_intake.sh
```

Automation-friendly mode:

```bash
./scripts/start_feature_intake.sh --non-interactive --json \
  --title "FEATURE_TITLE" \
  --problem "PROBLEM_STATEMENT" \
  --users "TARGET_USERS" \
  --in-scope "IN_SCOPE" \
  --out-of-scope "OUT_OF_SCOPE" \
  --acceptance "ACCEPTANCE_CRITERIA" \
  --constraints "CONSTRAINTS" \
  --non-functional "NON_FUNCTIONAL_REQUIREMENTS" \
  --risks "RISKS" \
  --done "DEFINITION_OF_DONE"
```

### End-to-End Feature Flow (with Gate A)

Bootstrap:

```bash
./scripts/feature_delivery_flow.sh bootstrap --non-interactive --json \
  --title "FEATURE_TITLE" \
  --problem "PROBLEM_STATEMENT" \
  --users "TARGET_USERS" \
  --in-scope "IN_SCOPE" \
  --out-of-scope "OUT_OF_SCOPE" \
  --acceptance "ACCEPTANCE_CRITERIA" \
  --constraints "CONSTRAINTS" \
  --non-functional "NON_FUNCTIONAL_REQUIREMENTS" \
  --risks "RISKS" \
  --done "DEFINITION_OF_DONE"
```

Run implementation slice (requires explicit approval):

```bash
./scripts/feature_delivery_flow.sh run \
  --feature-dir specs/XXX-feature \
  --task "TASK_SLICE" \
  --allow "src/app,tests" \
  --approved
```

### Minimal single nested run

```bash
/bin/zsh -f -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "YOUR_TASK_PROMPT"'
```

### Tester + Generator + Reviewer wrapper

```bash
./scripts/run_multiagent.sh \
  -C /ABS/PATH/TO/REPO \
  -t "TESTER_TASK" \
  -g "GENERATOR_TASK" \
  -r "REVIEWER_TASK" \
  --retries 3 \
  --backoff 5,10,20 \
  --sandbox workspace-write
```

## Reliability Rules

- If `stdin is not a terminal`, use `codex exec` (not interactive `codex`).
- If `401 Unauthorized`, run `codex login` in the same environment/profile.
- Launch nested agents with `/bin/zsh -f -lc` to avoid unstable shell profiles.
- On transient API/network errors, retry each agent step up to 3 times with backoff.
- Keep prompts deterministic: exact output paths, exact format, explicit restrictions.
- Treat a run as acceptable if the expected handoff artifact exists even when transport exits non-zero.

## Safety Rules

- Never allow unrestricted edits when scope can be narrowed.
- For critical tasks always include reviewer step.
- Never skip final orchestrator verification.

## Done Criteria

Consider multi-agent task complete only when all are true:
1. Tester/generator/reviewer handoff artifacts exist in `tmp/` and match scope.
2. Reviewer produced audit with expected format.
3. Orchestrator checks passed (tests/lint/diff/coverage as applicable).
4. Scoped coverage target is met (default `100%`) or documented exceptions are explicitly approved.
5. No out-of-scope files changed.

## Script Helper

Use bundled wrapper when you want one command for tester+generator+reviewer:

```bash
./scripts/run_multiagent.sh \
  -C /ABS/PATH/TO/REPO \
  -t "TESTER_TASK" \
  -g "GENERATOR_TASK" \
  -r "REVIEWER_TASK"
```

Notes:
- Script runs tester, generator, then reviewer (legacy executor/reviewer mode remains available via `-e`).
- Default sandbox is `workspace-write` (override with `--sandbox`).
- Script uses retries + backoff and `zsh -f` for nested stability.
- If reviewer writes `tmp/reviewer_out.json` or `tmp/agent_audit.txt`, script prints handoff/audit.
- Orchestrator checks (`pytest`, `make lint`, `git diff`) are still mandatory.

## Strict JSON Templates (Schema 1.0)

Wrapper validates handoffs strictly (`missing keys`, `extra keys`, `type mismatch` => FAIL).

Tester (`tmp/tester_out.json`):
```json
{
  "schema_version": "1.0",
  "role": "tester",
  "status": "NEEDS_WORK",
  "summary": "Added failing tests for X.",
  "changed_files": ["tests/test_x.py"],
  "checks": ["pytest -q tests/test_x.py: fail"],
  "artifacts": ["tmp/tester_out.json"],
  "next_action": "Generator should implement X.",
  "failing_reasons": ["expected 400, got 500"],
  "coverage": {
    "command": "pytest --cov=src/x --cov-report=term-missing",
    "percent": 72,
    "target_percent": 100,
    "uncovered_lines": ["src/x/service.py:44-61"]
  }
}
```

Generator (`tmp/generator_out.json`):
```json
{
  "schema_version": "1.0",
  "role": "generator",
  "status": "PASS",
  "summary": "Implemented X and stabilized tests.",
  "changed_files": ["src/x/service.py"],
  "checks": ["pytest -q: pass", "make lint: pass"],
  "artifacts": ["tmp/generator_out.json"],
  "next_action": "Reviewer validates requirements.",
  "implementation_notes": ["Added explicit null guard for config."],
  "coverage": {
    "command": "pytest --cov=src/x --cov-report=term-missing",
    "percent": 100,
    "target_percent": 100,
    "uncovered_lines": []
  }
}
```

Reviewer (`tmp/reviewer_out.json`):
```json
{
  "schema_version": "1.0",
  "role": "reviewer",
  "status": "PASS",
  "summary": "Requirements validated.",
  "changed_files": [],
  "checks": ["requirements review: pass"],
  "artifacts": ["tmp/reviewer_out.json", "tmp/agent_audit.txt"],
  "next_action": "Orchestrator runs final checks.",
  "verdict": "PASS",
  "reason": "All acceptance checks satisfied.",
  "requirements": ["R1=PASS", "R2=PASS"]
}
```

## Coverage Auto-Gate

Use wrapper-level coverage enforcement when you need deterministic gate behavior:

```bash
./scripts/run_multiagent.sh \
  -C /ABS/PATH/TO/REPO \
  -t "TESTER_TASK" \
  -g "GENERATOR_TASK" \
  -r "REVIEWER_TASK" \
  --coverage-cmd "pytest --cov=src/app/services/x --cov-report=term-missing" \
  --coverage-fail-under 100
```

Behavior:
- Runs coverage command right after generator step.
- Fails run if command exits non-zero.
- If `--coverage-fail-under` is set, parses coverage percent from log and fails when below threshold.
- Stores coverage log and gate summary in `tmp/runs/<run_id>/logs/coverage.log` and `tmp/runs/<run_id>/handoffs/coverage_gate.json`.

## Pattern Testing

Recommended checks for the orchestration pattern:
- Deterministic local smoke in pytest with mocked `codex` binary (no network/auth dependency).
- Optional live readiness probe by running one tiny real `codex exec` task and validating handoff files.

Live readiness probe command:
```bash
./scripts/check_codex_ready.sh -C /ABS/PATH/TO/REPO --timeout-sec 90
```
