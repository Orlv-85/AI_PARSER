# Prompt: split core/ingestion/pipeline.py into a package, with a monkeypatch guard (2026-10-24)

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. One PR, **move-only, no behavior change**.
Report to the coordinator (the session that started you) at the end. Do not ask the owner.

Owner decision 2026-10-24: a 1477-line module is not acceptable; split it. This overrides "leave"
in `docs/plan-split-overloaded-modules-2026-10-21.md`; the risk named there (tests patch ~21 names
on this module 82+ times; a moved function would silently stop seeing the patch) is handled by a
guard test instead.

## Read first

`AGENTS.md`; `docs/plan-split-overloaded-modules-2026-10-21.md` (General rules, `pipeline.py`
paragraph); `src/app/core/ingestion/pipeline.md`; `src/app/core/ingestion/pipeline.py`; every test
that imports or patches it (`git grep -n "ingestion.pipeline\|ingestion import pipeline" tests src scripts`).

## Steps

1. Worktree: `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch` then
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add ../AI_PARSER-wt-split-pipeline -b refactor/split-pipeline-20261024 origin/master`.
   Work only there; checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/<tool>`.

2. **Baseline**: run the full pytest and save the pass count; save the list of all monkeypatch
   targets on the pipeline module (quoted strings `"app.core.ingestion.pipeline.X"` and
   `monkeypatch.setattr(<pipeline module object>, "X", ...)`), with file:line.

3. **Guard test first** (commit it before moving anything, it must pass on the unsplit code):
   `tests/unit/test_monkeypatch_targets.py`. For every test file under `tests/`, find monkeypatch
   targets on modules under `app.` (both forms above; resolve module-object aliases from the file's
   imports). For each (module, NAME) assert: the module defines or imports NAME, **and** the
   module's own source reads NAME somewhere other than its definition/import line (AST: a `Name`
   load or an `Attribute` access of it inside a function body of that module). A patch on a module
   that never reads the name fails with "patch on <module>.<NAME> has no effect: no reader in this
   module". Keep it generic (not pipeline-only) and fast. If it already fails on master for some
   other module, list those in an explicit `KNOWN_NO_READER` set with a comment and report them;
   do not fix them here.

4. **Split**: `src/app/core/ingestion/pipeline/` package. `git mv pipeline.py pipeline/__init__.py`
   is NOT the goal: the goal is several modules by concern, each under ~400 lines, e.g. (decide from
   the code, keep the flow of `pipeline.md`):
   - `cycle.py` - `run_fetch_cycle` and the run loop / summary;
   - `sources.py` - source selection, YAML upsert, fetch state;
   - `rss.py` / `html_links.py` - per-type fetch (HTML two-stage block ~170 lines goes to
     `html_links.py`);
   - `admission_step.py` (or similar) - semantic admission / Jev calls from the pipeline;
   - `weekly_hooks.py` - `_record_weekly_observation`, `_publish_weekly_analytics_if_due` (weekly v2,
     deferred; move as is).
   `pipeline/__init__.py` re-exports only the public names that `src/`, `scripts/` and the CLI import
   today (list them), so production imports stay `from app.core.ingestion.pipeline import ...`.
   Use `git mv` for the largest part so history follows. No logic edits, no renames of functions.

5. **Re-point patches**: every test patch moves to the module that reads the name after the split
   (the guard decides). Where one name is read in two modules, patch both and say so. No test may
   patch the package `__init__` for a name that only a submodule reads.

6. Docs: `pipeline.md` header (`module:` = the module holding `run_fetch_cycle`, `covers:` gets
   `src/app/core/ingestion/pipeline/*.py`), Code map lists the new modules; the docstring of the
   main module names the doc; remove the `too-many-lines` disable. In
   `docs/plan-split-overloaded-modules-2026-10-21.md` add one line: "pipeline.py split 2026-10-24
   (owner decision), guard test `tests/unit/test_monkeypatch_targets.py`".

7. Checks: pytest pass count equals the baseline (+ the guard test); full gate:
   `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`. Move check: for every
   top-level definition of the old `pipeline.py`, compare its source (`ast.get_source_segment`) with
   the new location; all identical. Put the result (N definitions, N identical, list of any
   difference) in the report.

8. Commits: (a) guard test, (b) split; messages `test: guard that monkeypatches hit a reading module`
   and `refactor(ingestion): split pipeline.py into a package (move-only)`, each with
   `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Push;
   `gh pr create --base master --title "refactor(ingestion): split pipeline.py into a package (move-only)" --body "<module map with line counts, re-exports, patch re-points, guard test, move check, gate>"`.
   Do not merge.

## Report

PR link and head SHA; module map with line counts; public re-exports; number of patch targets
re-pointed; guard test result and any `KNOWN_NO_READER`; move check result; baseline vs final
pytest counts; anything unsure.
