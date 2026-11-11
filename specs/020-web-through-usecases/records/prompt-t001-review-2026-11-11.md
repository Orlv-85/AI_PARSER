# Review: spec 020, phase 1 (T001, T002)

Read-only review of the uncommitted diff in the current directory (`git diff`). Do not edit, commit
or use the network; do not spawn sub-agents. Run only:
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_layer_imports.py tests/unit/test_code_docs.py`

Read: `specs/020-web-through-usecases/spec.md` (FR-001..FR-003, User Story 1), `plan.md` ("Step 1
detail"), `tasks.md` (T001, T002), `specs/020-web-through-usecases/records/prompt-t001-t002-2026-11-11.md`,
then the diff of `src/app/README.md` and `tests/unit/test_layer_imports.py`.

Check:
1. Does `storage_imports` give the stated result for every form in the prompt, and can any import
   of `app.storage` (static, inside a function, literal `import_module` / `__import__`, wildcard,
   `from app import storage`) slip past `test_entry_points_import_storage_only_in_listed_files`?
   Try a few sources in a Python shell if needed.
2. Are `STORAGE_IN_ENTRY_POINTS` and `COMMITS_IN_WEB` right for the current code (grep), and do
   the tests fail when a file is added or fixed (equality, not subset)?
3. Can `web/app.py` import more than `SessionLocal` and `create_all` without a test failing?
4. README bullet: matches FR-001..FR-003, names existing tests, style of the section.
5. Anything else that is wrong or weak (false negatives of `calls_commit`, e.g. `await
   session.commit()`, `self._session.commit()`).

Report: findings with severity (blocker / should fix / note), file:line, the fix. No praise.
