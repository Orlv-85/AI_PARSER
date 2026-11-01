# Prompt: backlog T2, measure and plan the refactoring (2026-11-01)

You measure the code quality of `ai-news-collector` (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`)
and write a refactoring plan split into small PRs. **No code changes, no commits, no PR** in this
step. Report in English. No ssh, no paid calls.

## Context

Backlog item T2 in `docs/backlog/tooling-todo.json` (read it on `origin/master`): refactor complex,
duplicated and dead code found by crapper, dryer and mutator. The owner wants it done before the
next feature work. Rough numbers from 2026-11-01: crapper `--no-coverage` on `src`: about 100
functions with cyclomatic complexity >= 10; dryer on `src`: 9 duplicate pairs.

## Rules

- Work in your own temporary worktree of `origin/master` under your scratchpad (`git worktree add
  --detach`); remove it at the end. Never edit, commit or pull in
  `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself.
- Python: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python` (venv1 has
  `coverage` and `pytest`). Read `AGENTS.md` and the `ub-mode` skill (`~/.claude/skills/ub-mode/SKILL.md`,
  "Repository rules come first" applies).
- Tools: `~/tools/unclebob/crapper/crapper`, `~/tools/unclebob/dryer/dryer`,
  `~/tools/unclebob/mutator/mutator` (read their READMEs). Do not let them install anything into
  `venv1`; if crapper's own coverage run does not work with this repo's layout, run pytest under
  coverage yourself (`coverage run -m pytest -o addopts="" -q` then `coverage lcov`) and use
  `--use-existing-coverage`. Mutator: at most one small module (`src/app/core/world/filter.py`)
  with its own test file as `--test-command`, `--max-workers 2`, to judge test strength; no
  project-wide mutator run.
- Dead code: `vulture` may be used from a separate temp venv in your scratchpad (not `venv1`), as a
  hint only. For each candidate check callers: CLI commands, scripts and systemd units, tests,
  dynamic imports, Alembic migrations, FastAPI routes and templates.

## Deliverable

Write the plan to `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/plan-t2-refactor-2026-11-01.md`
(the only file you write outside your scratchpad):

1. Measurements: tool versions, commands, real CRAP table (functions with CRAP >= 30, and count of
   10-30), dryer pairs >= 0.8 with locations, mutator result on the one module, dead-code
   candidates with the caller check result.
2. PR list in order, each small (one module or one duplicate group), with: files, what changes,
   which tests pin the behavior first (existing or to write), risk (low/medium/high), whether it
   touches a feature with a code doc (then the doc must stay true), and production-sensitive areas
   (ingestion, daily digest, deploy scripts) flagged.
3. What not to touch and why (for example generated migrations, code that a pending spec 018 step
   will rewrite: `src/app/core/world/`, `src/app/storage/world.py`).
4. Open questions, if any, marked "owner" only for product or money questions.

## Report (final message)

Path of the plan, the headline numbers, the first three PRs you recommend, and anything decided by
you (one line each).
