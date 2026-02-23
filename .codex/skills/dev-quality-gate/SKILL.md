---
name: dev-quality-gate
description: Use before commit/push on this repo to enforce final repo-wide quality checks (make lint and pytest), distinguish scoped checks from final gates, and prevent CI surprises after local-only validation.
---

# Dev Quality Gate (AI_PARSER)

Use this skill when:
- preparing a commit or push
- finishing a feature after scoped TDD work
- changing `pyproject.toml`, lint config, Python target/version, or CI-related tooling

## Rule

Scoped checks are for iteration only.

Before `git commit`/`git push`, run final repo-wide gates and report them explicitly:
- `make lint PYTHON=./venv1/bin/python`
- `./venv1/bin/pytest`

## Mandatory workflow

1. During implementation
- You may run scoped tests/linters on touched files for speed.
- Mark them as `scoped` in updates/final notes.

2. Before commit
- Run repo-wide lint (`make lint`).
- Run repo-wide tests (`pytest`) unless user explicitly approves skipping.
- If either fails, fix or stop and report.

3. Before push
- Confirm the final commands and results in the response.
- Do not claim “all checks passed” if only scoped checks were run.

## Mandatory repo-wide gate triggers

If any of these files/settings change, repo-wide lint/tests are required (no scoped-only exception):
- `pyproject.toml`
- `Makefile`
- `build/Dockerfile`
- `.github/workflows/*`
- `ruff`/`mypy`/`pylint` settings
- Python version constraints/targets

## Reporting template

- `Scoped checks:` ...
- `Final repo-wide lint:` pass/fail (`make lint ...`)
- `Final repo-wide tests:` pass/fail (`pytest`)
- `Residual risk:` only if something was skipped/failed

