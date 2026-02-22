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
  - `tmp/tester_out.md`
  - `tmp/generator_out.md`
  - `tmp/reviewer_out.md`
- Define a scoped coverage target up front (default: `100%` for touched files / target modules in this task).
- Define the exact coverage command and report format to avoid ambiguity.
- Avoid prompts like "fix everything" without scope.

### 2) Run Tester

```bash
/bin/zsh -f -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "TESTER_TASK. Modify only tests and write tmp/tester_out.md."'
```

Tester responsibilities (explicit):
- Start with failing tests for the requested behavior.
- After generator reaches green once, add strengthening tests for edge cases and regressions.
- Drive coverage to the agreed scoped target (default `100%`).
- Write in `tmp/tester_out.md`:
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
- Write handoff summary to tmp/generator_out.md
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

Recommended generator handoff fields in `tmp/generator_out.md`:
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
/bin/zsh -f -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "Validate RESULTS against REQUIREMENTS. Write tmp/reviewer_out.md and tmp/agent_audit.txt with PASS or FAIL on line 1 and one short reason on line 2. Do not modify files outside tmp/."'
```

Reviewer prompt template:

```text
Review executor changes for TASK_X.
Validation:
- Requirement 1
- Requirement 2
Output file:
- tmp/reviewer_out.md
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

### Minimal single nested run

```bash
/bin/zsh -f -lc 'codex exec -C /ABS/PATH/TO/REPO --sandbox workspace-write "YOUR_TASK_PROMPT"'
```

### Tester + Generator + Reviewer wrapper

```bash
~/.codex/skills/multi-agent-orchestration/scripts/run_executor_reviewer.sh \
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
~/.codex/skills/multi-agent-orchestration/scripts/run_executor_reviewer.sh \
  -C /ABS/PATH/TO/REPO \
  -t "TESTER_TASK" \
  -g "GENERATOR_TASK" \
  -r "REVIEWER_TASK"
```

Notes:
- Script runs tester, generator, then reviewer (legacy executor/reviewer mode remains available via `-e`).
- Default sandbox is `workspace-write` (override with `--sandbox`).
- Script uses retries + backoff and `zsh -f` for nested stability.
- If reviewer writes `tmp/reviewer_out.md` or `tmp/agent_audit.txt`, script prints handoff/audit.
- Orchestrator checks (`pytest`, `make lint`, `git diff`) are still mandatory.
