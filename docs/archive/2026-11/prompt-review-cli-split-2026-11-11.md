# Review: CLI split (branch refactor/cli-thin-commands, commit 13620fd)

Read-only review. Do not edit files, commit, push or use gh; no network. Do not spawn sub-agents.

Change: `src/app/cli/main.py` (729 lines) split into one module per command group
(`articles.py`, `site.py`, `daily.py`, `periods.py`, `candidates.py`, `archive.py`,
`bulletin.py`, `world.py`), shared checks in `common.py`, composition root `deps.py`. The plain
`period-signals` run moved to `run_week_and_month` in `src/app/usecases/periodic/period_run.py`.
Rules: `src/app/cli/main.md`. The old file: `git show HEAD~1:src/app/cli/main.py`.

Check, with concrete inputs:
1. Behavior parity per command against the old file: options, defaults, error messages, exit
   codes, output (JSON key order, `sort_keys` or not, stderr vs stdout), order of
   `create_all`/session/logging calls, dry-run paths that must not call `create_all`.
2. `common.py` helpers reproduce each old message exactly (`completed_day`, `parse_day`,
   `check_usd`, `day_within_cap`).
3. `run_week_and_month`: same errors propagate as before (week `PeriodRunError` -> exit 2, month
   failure -> `{"state": "error", ...}` with rollback).
4. Tests: every former `cli_main` patch now hits the module that reads the name; the guard change
   in `tests/unit/test_monkeypatch_targets.py` does not hide a dead patch.
5. Docs: `src/app/cli/main.md` matches the code; references to `cli/main.py` elsewhere updated.

Run only: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:warnings tests/unit/test_cli_main.py tests/unit/test_cli_period_signals.py tests/unit/test_monkeypatch_targets.py tests/unit/test_layer_imports.py`

Report: findings first, each with file:line, severity, a concrete failing input and a fix; then
"no findings" for the checks that passed. Short.
