# Review prompt: spec 019 step 2 (use cases move to app/usecases), PR 221

You review PR 221 of the repo in the current directory (branch `refactor/019-usecases`, base
`master`). Read-only: do not edit, commit, push or switch branches. Do not run the full test suite
(it was run: exit 0); scoped commands are fine. Python: `./.venv/bin/python`.

## Context

Read `specs/019-layer-boundaries/spec.md`, `plan.md`, `tasks.md` (Phase 2 and 3) and the section
"Layers" of `src/app/README.md`. The PR claims to be a pure move: use-case modules go from
`src/app/core/` to `src/app/usecases/`, `digest_title` goes to `src/app/core/daily/titles.py`, and
references are rewritten. No logic change.

## What to check

1. Pure move. `git diff -M master...HEAD --stat` and, for the renamed Python files, that the only
   changed lines are imports and paths in docstrings. Report any other changed line.
2. Stale references to the old places that the rewrite missed, anywhere that is not history
   (`specs/`, `docs/archive/`, `docs/work/` are history and are not updated): old dotted names
   (`app.core.daily.enrichment`, `app.core.daily.signals` as a module, `app.core.ingestion.pipeline`,
   `app.core.archive`, `app.core.world_*`, `app.core.bulletin.daily`, `app.core.bulletin.writer_run`,
   `app.core.periodic.period_run`, `app.core.periodic.period_brief_run`,
   `app.core.sources.onboarding`, `app.core.sources.validation`), old file paths, strings built
   from parts (`SRC / "core" / ...`, f-strings), `python -m` calls, Dockerfile, compose files,
   workflows, `pyproject.toml` (package data, mypy, coverage), `Makefile`, Alembic `env.py`.
3. Tests that now pass for the wrong reason: a test that scans imports or paths by an old prefix
   and so checks nothing after the move. Two were found and fixed
   (`test_archive_not_imported_by_web_or_mcp`, the web check in `tests/unit/test_world_storage.py`);
   look for more.
4. `tests/unit/test_layer_imports.py`: does it really enforce the rules in "Layers"? Try to name an
   import form it would miss (relative imports, `importlib`, `__import__`).
5. Feature docs: the six moved docs and the docs that stayed. Wrong statements about where code
   lives now (prose, code maps), not only backticked paths.
6. Anything in runtime that depends on a module path: logger names, entry points in
   `pyproject.toml`, strings stored in the database or journals that contain a module path.

## Report

Reply with a list of findings, each: severity (blocker / should fix / note), file and line, what is
wrong, what you checked to be sure. Say plainly what you did not check. No praise, no summary of the
PR. If you find nothing in a point, say "nothing found" for that point.
