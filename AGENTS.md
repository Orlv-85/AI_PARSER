# AGENTS.md

## Purpose

This repository contains `ai-news-collector`, a Python 3.14 application for collecting and serving AI news from configured RSS/HTML sources.

When working in this repo, optimize for small, testable changes that preserve existing CLI, API, and ingestion behavior.

## Stack

- Python `3.14`
- FastAPI web app in `src/app/web`
- Typer CLI exposed as `ai-news`
- SQLAlchemy + Alembic for storage and migrations
- SQLite for local/dev, PostgreSQL for production
- Tests in `tests/`

## Repo Layout

- `src/app/` - application code
- `tests/` - unit and e2e tests
- `scripts/` - operational and deploy scripts
- `sources.yaml` - source registry for RSS/HTML ingestion
- `.specify/specs/` - feature specifications and change context
- `README.md` - setup, run, deploy, and operator commands

## Local Environment

- Prefer `venv1` for local commands in this repo.
- Default Python for lint/test commands: `./venv1/bin/python`
- Default pytest invocation: `./venv1/bin/pytest`
- If a command depends on project imports, run it from the repo root.

## Working Rules

- Read relevant files before changing code; do not infer architecture from file names alone.
- Prefer minimal patches that match the current code style and structure.
- Preserve backward compatibility for CLI flags, API responses, and stored data unless the task explicitly requires a break.
- Do not edit unrelated files just because they are nearby.
- Do not overwrite user changes in a dirty worktree.
- For behavior changes, read the closest relevant spec in `.specify/specs/` before editing.

## Code Changes

- Use `apply_patch` for manual file edits.
- Keep code ASCII unless a file already requires Unicode.
- Add comments only where logic is non-obvious.
- Follow existing naming and module organization; avoid speculative refactors.
- When changing parsing or ingestion behavior, check surrounding tests first and extend coverage for regressions.

## Feature Docs Next To Code

- Every feature keeps a short technical doc next to its main code file: `<main_module>.md` in the
  same folder (example: `src/app/core/daily_signals.md` for `daily_signals.py`).
- Content is dry and technical: flow, module map, tables, version constants, invariants, "where to
  change what", tests. No history, no rationale essays; operator commands stay in `docs/`.
- The main module's docstring names the doc (`... : <main_module>.md next to this file.`).
- A change to the feature's behavior, structure or names updates that doc in the same change.
- New features add the doc and the docstring line as part of the implementation.
- Start the doc with a header so `scripts/check_code_docs.py` can check it:
  `<!-- code-doc` / `module: <main module path>` / `covers:` / `  - <glob of the feature files>` / `-->`.
- Sync is checked: pytest (`tests/unit/test_code_docs.py`) fails when a backticked file, constant,
  class, function, flag or `AINEWS_*` setting in a doc no longer exists; CI fails when covered files
  change without the doc. A change that needs no doc update (pure rename, formatting) says so with a
  commit message line `Docs-Skip: <reason>`.
- System overview: `src/app/README.md` (packages, entry points, code docs list).
- Register a new code doc in `docs/README.md` ("Code docs") and in the `README.md`
  "Documentation" section. `docs/` keeps general docs, operator guides and dated records only.

## Validation

For scoped changes, run the smallest useful check first.

- Scoped lint: `./venv1/bin/python -m ruff check src tests`
- Scoped tests: `./venv1/bin/pytest <target>`
- Shell syntax (for script changes): `bash -n scripts/*.sh .codex/skills/multi-agent-orchestration/scripts/*.sh`

Before commit or push, run the final repo-wide quality gate:

- `make lint PYTHON=./venv1/bin/python`
- `./venv1/bin/pytest`

For multi-agent orchestration changes, also run targeted smoke tests:

- `./venv1/bin/pytest tests/unit/test_multiagent_wrapper_script.py tests/unit/test_check_codex_ready_script.py -q`

If full validation is too expensive or blocked, state exactly what was not run and why.

Do not report "all checks passed" if only scoped checks were run.

## Source Configuration Changes

When editing `sources.yaml`:

- Preserve existing schema and field naming.
- Prefer narrowly targeted selector changes over broad rewrites.
- Validate with the smallest relevant fetch/parser tests when available.
- Avoid removing sources unless the task explicitly requires it.

## Deploy And Ops

- Treat deploy scripts and workflow files as production-sensitive.
- Do not change deploy defaults, auth settings, ports, retention, or database behavior without an explicit requirement.
- For production-related edits, prefer consistency with `README.md`, `deploy/`, and `scripts/`.

## Web And Runtime

- Web entrypoint wrapper: `./run_web.sh`
- Actual web launcher: `scripts/run_web.sh`
- Default local web port: `8010`
- Default local web mode is PostgreSQL bootstrap unless overridden; do not silently change this behavior.
- If a task is only about local UI iteration or tests, prefer explicit env settings instead of changing runtime defaults.

## Multi-Agent Workflow

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

## Troubleshooting

- Before debugging a failing test, CI run, or runtime error, read `docs/troubleshooting.md`; it holds known cases (symptom, cause, fix) as JSON.
- After resolving a new non-obvious failure, add a case to that file in the same change.

## Specs

Relevant specs currently present:

- `001-ai-news-collector`
- `002-fetch-pipeline-optimization`
- `003-source-onboarding-management`
- `004-daily-digest-public-admin`
- `005-web-export-autoupdate`

When a task clearly maps to one of these areas, review the matching `spec.md` first and keep implementation aligned unless the user explicitly wants to diverge.

## Response Expectations

- Summarize what changed, why, and how it was validated.
- Include file references for non-trivial edits.
- Call out assumptions, risks, and skipped checks explicitly.

## Prompts For Other Sessions

- Always save every task or handoff prompt intended for another session to a file before delivering it to the user.
- Use `docs/prompt-<task>-<YYYY-MM-DD>.md` with a descriptive task name; preserve earlier prompts instead of overwriting unrelated files.
- Include a clickable file link in the response. Inline prompt text is optional and does not replace the saved file.
- Preserve this user preference in session-context and handoff artifacts so future sessions follow it.
