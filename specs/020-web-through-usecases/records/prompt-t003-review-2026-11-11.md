# Review: spec 020, phase 2 (T003-T005)

Read-only review of the uncommitted diff in the current directory (`git diff`, plus the new file
`tests/unit/test_web_table_init.py`). Do not edit, commit or use the network; do not spawn
sub-agents. Run only:
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_web_table_init.py tests/unit/test_web_app.py tests/unit/test_web_source_onboarding_api.py tests/unit/test_web_home_page.py tests/unit/test_code_docs.py tests/unit/test_layer_imports.py`

Read: `specs/020-web-through-usecases/spec.md` (User Story 2, Edge Cases, FR-004), `plan.md`
("Step 2 detail"), the executor prompt
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/specs/020-web-through-usecases/records/prompt-t003-t005-2026-11-11.md`
and its report `specs/020-web-through-usecases/records/report-t003-t005-2026-11-11.md`.

Check:
1. `_once` and its wiring in `create_app`: flag set only after success; exception leaves it
   unset; one lock shared by both; each app instance fresh; the module-level `create_all` is read
   at build time as before (tests patch it before `create_app`).
2. Every former `Base.metadata.create_all(bind=onboarding_engine)` call in `routes/sources.py`
   now calls `deps.create_onboarding_tables()` inside the same `try`; no handler logic, status
   code or other behavior changed; nothing left that still creates tables per request.
3. Tests: do they prove the rule (would they fail if the flag were set before `create`, if the two
   wrappers had separate locks, if the flag were global)? Are they flaky (thread timing, global
   `Base.metadata.create_all` patch leaking, `get_settings` cache)?
4. Docs: `pages.md` and `onboarding.md` match the code, name existing tests, no contradiction
   left with the old 2026-11-06 decision; `app.py` not added to `covers:`.
5. Lock risk: can holding the lock while `create` runs block requests in a way the old code did
   not (for example a hanging database at first request)? Say whether it matters.

Report: findings with severity (blocker / should fix / note), file:line, the fix. No praise.
