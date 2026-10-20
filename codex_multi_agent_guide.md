# AI News Collector --- Codex Multi-Agent Execution Guide

## Overview

This document is a ready-to-use instruction for Codex to execute a
Spec-Driven Development workflow using multi-agent orchestration.

## Goal

Implement the project strictly following Spec Kit artifacts:

-   .specify/memory/constitution.md\
-   specs/001-ai-news-collector/spec.md\
-   specs/001-ai-news-collector/plan.md\
-   specs/001-ai-news-collector/tasks.md

## Multi-Agent Pattern (MANDATORY)

You must use 3 agents:

1.  Builder --- writes code (only current task)
2.  Reviewer --- validates against spec
3.  Runner --- executes commands/tests

Agents are spawned via zsh shell using Codex.

------------------------------------------------------------------------

## Orchestrator Prompt

Paste this into Codex:

    You are the Orchestrator.

    Follow Spec Kit artifacts in .specify.

    Use MULTI-AGENT pattern:
    - Builder
    - Reviewer
    - Runner

    Execution rules:
    - Implement tasks sequentially (T1 → T12)
    - NEVER skip tasks
    - NEVER implement future tasks early

    Workflow:
    1. Spawn Builder
    2. Spawn Reviewer
    3. Spawn Runner
    4. If OK → next task

    Hard rule:
    Do not proceed until:
    - Reviewer has ZERO BLOCKERS
    - Runner passes

    Start with Task T1 only.

------------------------------------------------------------------------

## Builder Command

    cat > /tmp/builder.txt <<'EOF'
    You are Builder.

    Implement ONLY Task T1.

    Follow spec + plan strictly.

    Output:
    - file tree
    - full file contents
    EOF

    zsh -lc 'codex exec --output-last-message /tmp/builder_out.md "$(cat /tmp/builder.txt)"'

------------------------------------------------------------------------

## Reviewer Command

    cat > /tmp/reviewer.txt <<'EOF'
    You are Reviewer.

    Check:
    - scope (only T1)
    - correctness vs spec

    Return:
    BLOCKER / WARNING / OK
    EOF

    zsh -lc 'codex exec --output-last-message /tmp/reviewer_out.md "$(cat /tmp/reviewer.txt)"'

------------------------------------------------------------------------

## Runner Command

    cat > /tmp/runner.txt <<'EOF'
    You are Runner.

    Run:
    - python --version
    - install deps
    - ruff check .
    - pytest

    Return raw output only.
    EOF

    zsh -lc 'codex exec --output-last-message /tmp/runner_out.md "$(cat /tmp/runner.txt)"'

------------------------------------------------------------------------

## Rules

-   Always read .specify files before acting
-   Never hallucinate missing requirements
-   Prefer minimal code
-   Comments in English

------------------------------------------------------------------------

## How to Use

1.  Place this file into your repo
2.  Open Codex
3.  Paste Orchestrator Prompt
4.  Let it execute commands

------------------------------------------------------------------------

Generated at: 2026-02-21 12:48:05.096035

## Repo scripts (moved from AGENTS.md, 2026-10-20)

- New feature intake + Spec Kit bootstrap:
  - `./scripts/start_feature_intake.sh`
  - Non-interactive mode for automation:
    - `./scripts/start_feature_intake.sh --non-interactive --json --title "..." --problem "..." --users "..." --in-scope "..." --out-of-scope "..." --acceptance "..." --constraints "..." --non-functional "..." --risks "..." --done "..."`
- One-command feature flow (bootstrap + guarded run):
  - `./scripts/feature_delivery_flow.sh bootstrap ...`
  - `./scripts/feature_delivery_flow.sh run --feature-dir specs/XXX-feature --task "..." --allow "..." --approved`
- Canonical repo entrypoint: `./scripts/run_multiagent.sh`
- Readiness probe (live `codex exec` check): `./scripts/check_codex_ready.sh -C /ABS/PATH/TO/REPO --timeout-sec 90`
- Required handoff artifacts are strict JSON:
  - `tmp/tester_out.json`
  - `tmp/generator_out.json`
  - `tmp/reviewer_out.json`
- Keep per-run artifacts in `tmp/runs/<run_id>/` (prompts, logs, messages, handoffs).
- If coverage gate is required, use wrapper flags:
  - `--coverage-cmd "<coverage command>"`
  - `--coverage-fail-under <percent>`

Smoke tests for changes to these scripts:

- `./venv1/bin/pytest tests/unit/test_multiagent_wrapper_script.py tests/unit/test_check_codex_ready_script.py -q`
