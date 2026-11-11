# Review prompt: spec 020 T009 (source onboarding handlers call use cases)

You are a read-only reviewer. Do not edit files, commit, push or use the network. Do not spawn
sub-agents.

Worktree: /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-020-t009, branch
`refactor/020-t009-onboarding`. The change is `git diff origin/master...HEAD` (one commit).

Context to read: `AGENTS.md`; `specs/020-web-through-usecases/spec.md` (FR-001, FR-003, SC-002),
`tasks.md` (T009); `src/app/usecases/sources/onboarding.md` (Access rule on handlers, Decisions
on response models and two engines, Code map).

The change is a refactor: no change for API answers (status codes, bodies, `detail` strings,
OpenAPI incl. component names), stored data, CLI or paid calls.

Check:
1. Each of the 14 `/api/source-onboarding/*` handlers in `src/app/web/routes/sources.py` keeps
   the same behavior: same session factory, same commit points (write actions commit, reads do
   not), same exceptions mapped to the same codes, `create_onboarding_tables()` still inside the
   `try`, validate still runs in the thread pool.
2. `import_batch`, `candidate_overlaps` (`usecases/sources/onboarding.py`), `validate_batch`
   (`usecases/sources/validation.py`), `review_in_session` (`usecases/sources/candidate_review.py`):
   values read after commit are the same as before (expire_on_commit), sessions closed on errors.
3. The moved modules (`usecases/sources/intake.py`, `candidate_review.py`) are byte-equal to the
   old `web/source_intake.py`, `web/source_onboarding.py` apart from imports, the docstrings, the
   moved response models and `review_in_session`.
4. Tests: retargeted monkeypatches still hit a reader (the patched name is looked up at call time
   in the patched module); no test lost an assertion.
5. Doc: `onboarding.md` matches the code; no stale paths left in `src/`, `tests/`, `docs/`
   (outside `docs/archive`), `README.md`.

Run only: `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-020-t009 && PYTHONPATH=src
/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:cacheprovider
tests/unit/test_layer_imports.py tests/unit/test_web_source_onboarding_api.py
tests/unit/test_web_source_onboarding_view.py tests/unit/test_source_intake.py
tests/unit/test_source_onboarding_service.py tests/unit/test_monkeypatch_targets.py
tests/unit/test_web_route_table.py`

Report (short): findings ranked by severity, each with file:line, the failing scenario and a fix;
then "no findings" items you checked. No praise, no summary of the change.
