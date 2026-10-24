# Prompt: split core/daily/signals_compute.py (move-only) and fix two no-effect test patches (2026-10-24)

Repo: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. One PR, **no behavior change**. Report to the
coordinator (the session that started you) at the end. Do not ask the owner.

Owner decision 2026-10-24: ~800-line modules are not acceptable; split. This overrides "leave" for
`signals_compute.py` in `docs/plan-split-overloaded-modules-2026-10-21.md`. `pipeline.py` was split
the same way in PR #106; the guard `tests/unit/test_monkeypatch_targets.py` checks that every test
patch hits a module that reads the name.

## Read first

`AGENTS.md`; `src/app/core/daily/signals.md` (Code map, Tests; pinned fixtures); 
`src/app/core/daily/signals_compute.py`; its importers (`git grep -n "signals_compute" src tests scripts`);
`tests/unit/test_monkeypatch_targets.py` (`KNOWN_NO_READER`); PR #106 as the example
(`gh pr view 106`).

## Steps

1. Worktree: `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch` then
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add ../AI_PARSER-wt-split-signals -b refactor/split-signals-compute-20261024 origin/master`.
   Checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/<tool>`. Save the baseline pytest count.

2. **Split** `signals_compute.py` into modules of one concern each, every module under ~400 lines,
   decided from the code. Options: a package `core/daily/signals_compute/` (like #106) or sibling
   modules `core/daily/signals_<part>.py` next to the existing `signals_*.py` - pick the one that
   matches the current layout of `core/daily/` and say why. The `_Snapshot` class stays whole in one
   module. Keep the public names importable from where `src/` imports them today (re-export only
   those, list them). `git mv` for the largest part; no logic edits, no renames.

3. Re-point test patches and imports; the guard test must pass with no new `KNOWN_NO_READER` entry.

4. **Separate commit, test-only**: fix the two existing no-effect patches listed in
   `KNOWN_NO_READER` (`app.core.sources.candidates.group_candidate_overlaps` in
   `tests/unit/test_source_candidate_repo.py:254`, `app.core.daily.signals.run_signals` in
   `tests/unit/test_web_daily_signals_api.py:48`): patch the module that reads the name, check the
   test still asserts what its name says (if the patch never took effect, the test may have been
   passing for the wrong reason: make it check the intended behavior, say what changed), then empty
   `KNOWN_NO_READER`.

5. Docs: `signals.md` header `covers:` / Code map for the new modules; docstring of the main module
   names the doc; one line in `docs/plan-split-overloaded-modules-2026-10-21.md`:
   "signals_compute.py split 2026-10-24 (owner decision)".

6. Checks: move check - for every top-level definition of the old file compare
   `ast.get_source_segment` with the new location (report N / identical / differences); pinned
   signal fixtures unchanged (`git diff --stat origin/master -- tests/fixtures` empty, or the
   equivalent path); pytest count = baseline; full gate:
   `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.

7. Commits `refactor(signals): split signals_compute.py (move-only)` and
   `test: make two patches hit the module that reads them`, each with
   `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Push;
   `gh pr create --base master --title "refactor(signals): split signals_compute.py (move-only)" --body "<module map with line counts, layout choice, re-exports, move check, the two patch fixes, gate>"`.
   Do not merge.

## Report

PR link and head SHA; module map with line counts and the layout choice; re-exports; move check;
fixtures unchanged; what the two fixed tests check now; baseline vs final pytest counts; anything
unsure.
