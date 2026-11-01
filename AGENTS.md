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
- `specs/<NNN>-<name>/` - feature specs (`spec.md`, `plan.md`, `tasks.md`) and `records/` (prompts, reviews, reports of that feature)
- `.specify/` - Spec Kit: `templates/` is the format of new specs; `scripts/` and `memory/constitution.md`
  are Codex-era history, not current rules; no specs here
- `docs/` - operator guides only (deploy, configuration, cli, troubleshooting, feature guides);
  `docs/work/` - open process files (coordinator state, active prompts); `docs/backlog/` - backlog
  JSON; `docs/archive/<YYYY-MM>/` - finished prompts, plans, reports, old states
- `README.md` - setup, run, deploy, and operator commands

## Local Environment

- Prefer `.venv` for local commands in this repo (`venv1` may exist as a symlink to it for older prompts).
- Default Python for lint/test commands: `./.venv/bin/python`
- Default pytest invocation: `./.venv/bin/pytest`
- If a command depends on project imports, run it from the repo root.

## Working Rules

- Read relevant files before changing code; do not infer architecture from file names alone.
- Prefer minimal patches that match the current code style and structure.
- Preserve backward compatibility for CLI flags, API responses, and stored data unless the task explicitly requires a break.
- Do not edit unrelated files just because they are nearby.
- Do not overwrite user changes in a dirty worktree.

## Owner And Questions

- The owner takes part minimally: design questions and doc reviews go to another session or model,
  not to the owner.
- Never settle an open question silently. When a question comes up (design choice, missing reason,
  doubtful or dead code, a change of what readers see or what is paid), always notify the owner in
  the reply: one line per question, how it was settled (found with source / decided by the agent)
  or, if it needs the owner, a yes/no question with a recommendation.
- Only product questions (what readers see) and money questions (paid calls, budgets) wait for the
  owner's answer; everything else is decided by the agent and reported.

## Code Changes

- Use `apply_patch` for manual file edits.
- Keep code ASCII unless a file already requires Unicode.
- Add comments only where logic is non-obvious.
- Follow existing naming and module organization; avoid speculative refactors.
- When changing parsing or ingestion behavior, check surrounding tests first and extend coverage for regressions.
- Test first (TDD): after the feature doc states the rule, write the failing test, run it and see it
  fail for the expected reason, then write the smallest code that makes it pass. For a bug, the
  failing test reproduces it before the fix. If an honest test is impractical, say so instead of
  writing a weak one.

## Feature Docs Next To Code

Markdown in `src/` is source, not documentation (Carson Gross, "Markdown in /src",
https://htmx.org/essays/markdown-in-src/): the feature doc holds the intended current behavior, and
code and tests follow it.

- Each feature has a doc next to its main module: `<main_module>.md` (example:
  `src/app/core/daily/signals.md`). The main module's docstring names it.
- Sections, short and dry:
  - Behavior - what the feature does and guarantees now: rules, not numbers (name the constant);
    a Mermaid diagram of the flow; each rule names the tests that check it (`Tests: ...`), and a
    rule without a test says so;
  - Decisions - decision and why, one or two lines each, no history;
  - Invariants;
  - Code map - flow, modules, tables, versions, where to change what;
  - Tests.
  Operator commands stay in `docs/`; do not repeat Behavior there.
- Order of work: a behavior change starts in the doc. A feature plan edits the doc before the code;
  code and tests are derived from it; the doc ends up matching the code in the same change.
- `specs/<NNN>/` is the process (proposal, plan, tasks, records). When a feature ships, its lasting
  intent moves into the doc; the spec stays as history and is not kept current.
- Curated, not generated: an agent drafts or edits a doc only within its task, and a different
  session or model reviews it; no bulk generation of docs. Older features get a doc when they are
  next changed. A "why" that no source states is written as "decided <date> (agent): <reason>",
  never as history, and the owner is notified (see "Owner And Questions").
- Header: `<!-- code-doc` / `module: <path>` / `covers:` / `  - <glob>` / `-->`. Register the doc in
  `docs/README.md`, `README.md` and `src/app/README.md`.
- Checked by `scripts/check_code_docs.py`: pytest fails on stale names in a doc (code names in
  `src/`, `test_*` names in `tests/`); CI fails when covered files change without the doc (opt out:
  commit line `Docs-Skip: <reason>`).

## Validation

For scoped changes, run the smallest useful check first.

- Scoped lint: `./.venv/bin/python -m ruff check src tests`
- Scoped tests: `./.venv/bin/pytest <target>`
- Shell syntax (for script changes): `bash -n scripts/*.sh .codex/skills/multi-agent-orchestration/scripts/*.sh`

Before commit or push, run the final repo-wide quality gate:

- `make lint PYTHON=./.venv/bin/python`
- `./.venv/bin/pytest`

Quality tools of the `ub-mode` skill live outside the repo, one checkout each, with their own
`.venv` made on first run: `~/tools/unclebob/crapper`, `~/tools/unclebob/dryer`,
`~/tools/unclebob/mutator` (https://github.com/unclebob). Run them from the repo root on the files
your change touches; results go to `.metrics/` and coverage to `target/` (both git-ignored).

- CRAP per function (keep under 10): `~/tools/unclebob/crapper/crapper <files>`
- Duplication (fix pairs at 0.8 and above): `~/tools/unclebob/dryer/dryer --threshold 0.8 <files>`
- Mutation testing (start with one file): `~/tools/unclebob/mutator/mutator --test-command "./.venv/bin/pytest -q" <file>`

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

Codex multi-agent scripts (`scripts/run_multiagent.sh` and related; not in active use): see
`docs/archive/2026-10/codex_multi_agent_guide.md`, including its smoke tests.

## Troubleshooting

- Before debugging a failing test, CI run, or runtime error, read `docs/troubleshooting.md`; it holds known cases (symptom, cause, fix) as JSON.
- After resolving a new non-obvious failure, add a case to that file in the same change.

## Specs

All specs live in `specs/<NNN>-<name>/` (`ls specs/`). A spec is the working document of a feature
in progress; once the feature ships it is history and is not kept current.

- Before a behavior change, read the feature's code doc ("Feature Docs Next To Code"): it is the
  current behavior. Keep the implementation aligned with it unless the user explicitly wants to diverge.
- A new spec is written by the session in the format of `.specify/templates/` (`spec-template.md`,
  `plan-template.md`, `tasks-template.md`). The Spec Kit commands (`.codex/prompts/speckit.*`) and
  `.specify/scripts/` are Codex tooling kept for history, not used.
- Read `spec.md` / `plan.md` for a feature in progress, or for a shipped feature that has no code
  doc yet. In the latter case check its claims against the code: status lines ("Draft") of old specs
  were never updated.

## Response Expectations

- Summarize what changed, why, and how it was validated.
- Include file references for non-trivial edits.
- Call out assumptions, risks, and skipped checks explicitly.

## Prompts For Other Sessions

- Save every prompt for another session to a file before giving it to the user, and link it.
- Feature with a spec: `specs/<NNN>-<name>/records/prompt-<task>-<YYYY-MM-DD>.md`; reviews and
  reports of that feature go to the same `records/`. Other prompts: `docs/work/prompt-<task>-<YYYY-MM-DD>.md`
  (git-ignored while open), copied to `docs/archive/<YYYY-MM>/` in a docs PR when done. Plans and
  reports without a spec go the same way (`docs/work/`, then `docs/archive/`). Nothing dated stays
  in the root of `docs/`. Never overwrite earlier prompts.
- Keep this rule in handoff artifacts so future sessions follow it.
