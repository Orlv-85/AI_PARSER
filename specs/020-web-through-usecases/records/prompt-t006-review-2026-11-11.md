# Review: spec 020, phase 3 (T006-T008): JSON bodies through Pydantic

Read-only review of the uncommitted diff in the current directory (`git diff`). Written by the
coordinator (Claude), not by Codex. Do not edit, commit or use the network; do not spawn
sub-agents. Run only:
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_web_source_onboarding_api.py tests/unit/test_auth_stage1.py tests/unit/test_web_app.py tests/unit/test_web_home_page.py tests/unit/test_web_route_table.py tests/unit/test_code_docs.py`

Read: `specs/020-web-through-usecases/spec.md` (User Story 3, Edge Cases, FR-005, FR-006),
`plan.md` ("Step 3 detail", "Decisions"), then the diff: `src/app/web/models.py`,
`src/app/web/routes/sources.py`, `src/app/web/routes/pages.py`, the docs
`src/app/usecases/sources/onboarding.md` and `src/app/web/pages.md`, and the tests.
Compare with the old handlers: `git show HEAD:src/app/web/routes/sources.py` and
`git show HEAD:src/app/web/routes/pages.py`.

Check:
1. Same answers as before for every request that did not give 500 before: status, `detail`
   string, order of checks. Try inputs in a Python shell against both versions if needed
   (bools, numeric strings, `" 7 "`, `9.0`, `[0, null]`, `null` raw_text, extra keys, nested
   objects, huge numbers, `Infinity`/`NaN` literals, empty list). List every difference you find.
2. Bodies that gave 500 before now give the documented client error; nothing can still raise
   500 from body parsing (non-UTF-8 bytes, deeply nested JSON, a JSON with duplicate keys).
3. `_read_body` maps only whole-body errors to the "required" string; can a field error of
   another type reach it and give a misleading `detail`?
4. Login: auth off still answers 200 without reading the body; auth on, malformed body logs
   `login_failed` and answers 401; credentials still `str(value)`.
5. OpenAPI: the three operations unchanged (no `requestBody`, no 422); the route-table test
   change (`_is_blocked`) still catches a route that the middleware should block.
6. Docs match the code and name existing tests; the error order in `onboarding.md` is the real one.

Report: findings with severity (blocker / should fix / note), file:line, the fix. No praise.
