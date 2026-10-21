# Prompt: group `src/app/core` into feature packages; plan splits of overloaded files (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder. `venv1` is installed editable on the main folder: in the worktree run
checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path).

## Context

`src/app/core/` holds 28 flat modules of unrelated features (ingestion, daily signals, weekly
analytics, source onboarding). The owner wants them grouped logically, and wants to know which files
are overloaded. This task has two parts: **(1)** one PR that only moves modules into packages, no
behavior change; **(2)** a written plan (no code) for splitting overloaded files, reviewed before
anyone splits anything.

## Part 1: move modules into packages (one PR)

Target layout (adjust only with a stated reason, e.g. an import cycle):

```text
app/core/
  __init__.py            keep its current re-exports working
  models.py, categories.py, canonicalize.py, jev.py     shared by several features: stay here
  ingestion/   pipeline.py, pipeline.md, admission.py, scoring.py, dedup.py
  daily/       signals.py (daily_signals.py), signals.md (daily_signals.md), signals_compute.py,
               signals_entities.py, signals_extract.py, signals_brief.py, enrichment.py
               (daily_enrichment.py), rubric.py (daily_rubric.py), reenrich_pilot.py
  weekly/      analytics.py, audit.py, enrichment.py, frozen.py, input.py, narrative.py,
               topics.py, worker.py (from weekly_*.py)
  sources/     onboarding.py, review.py (from source_*.py)
```

Place `legacy_cleanup.py` by its callers (read it). Drop the redundant prefix in the new names
(`daily/daily_signals.py` -> `daily/signals.py`).

Rules:
- `git mv` every file so history follows; contents change only in imports and in names that point to
  module paths. No logic edits, no reformatting, no renamed functions or classes.
- Update every reference: imports in `src/`, `tests/`, `scripts/` (at least `digest_generator.py`,
  `legacy_articles_cleanup.py`, `reenrich_articles.py`, `reenrich_pilot.py`,
  `sources_onboarding_helper.py`, `weekly_frozen_report.py`, `check_code_docs.py`), monkeypatch
  strings in tests (`"app.core.pipeline.X"` and similar: grep for quoted module paths too),
  `docs/`, `README.md`, `src/app/README.md`, `specs/` only where a current doc links a path (specs
  are history: do not rewrite them).
- No compatibility shims at old paths: the package is internal and shims would make monkeypatching
  silently patch the wrong module. Check that nothing outside the repo imports `app.core.*`
  (deploy files, systemd units, compose, workflows); if something does, stop and report.
- Code docs: move `pipeline.md` and `daily_signals.md` with their modules, update the header
  (`module:`, `covers:` globs), the module docstrings that name them, the Code map paths, and the
  registrations in `docs/README.md`, `README.md`, `src/app/README.md`.
- Weekly analytics v2 is only moved, as is: its keep-or-delete decision is deferred until weekly
  work starts. Do not document or delete it.

Checks: `ruff`, full gate (`make lint PYTHON=...`, full `pytest`, same pass count as on
`origin/master`), `scripts/check_code_docs.py` and `--diff origin/master --strict`, and
`python -c "import app.cli.main, app.web.app, app.mcp"`-style smoke imports of every entry point
(CLI `ai-news --help`, web app factory, MCP server, each changed script with `--help` where it has one).

## Part 2: plan for overloaded files (no code; a file in the PR)

Write `docs/plan-split-overloaded-modules-2026-10-21.md`. Candidates by size on master:
`storage/repos.py` (1605 lines, 6 repo classes), `core/pipeline.py` (1446), `web/app.py` (1374, 39
routes in one `create_app`), `core/source_onboarding.py` (1005), `core/daily_signals_compute.py`
(799); check the rest of `src/app` for more (size, `too-many-*` pylint disables, mixed concerns).
Per file: what it mixes, the proposed split (target modules, what goes where), what the split costs
(import churn, monkeypatch strings in tests, code-doc changes), risk, and a recommendation
(split / leave, with a reason). Order the splits; one PR per file. Weekly v2 files: list them, no
recommendation (deferred).

## Output

- One PR with Part 1 and the Part 2 plan file. Do not merge.
- In your reply: the PR link; the final layout tree; any deviation from the target layout with its
  reason; the count of changed references by area (src, tests, scripts, docs); exact checks run with
  pass counts; the Part 2 summary as a table "file | lines | recommendation | one-line reason";
  open questions one line each (how settled, or a yes/no question for the owner with a
  recommendation, only if it changes what readers see or what is paid).
- Save any prompt you write for another session to a file per `AGENTS.md`.
