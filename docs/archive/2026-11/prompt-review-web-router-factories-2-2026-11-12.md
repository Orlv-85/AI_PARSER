# Review 2: web router factories (branch refactor/web-router-factories, commit f37b16d)

Read-only review. Do not edit files, commit, push or use gh; no network. Do not spawn sub-agents.

Review only `git diff 7f06b60 f37b16d` (the first commit was reviewed with no findings).
Change: the import and validate handlers of `src/app/web/routes/sources.py` and `list_news` /
`export_news` of `news.py` now delegate in one call (`_import_response`, async
`_validate_response` -> `_validated` in the thread pool, `_news_items`); new tests pin route
parameters and that handlers only delegate, plus tests for mutation survivors.

Check, with concrete inputs:
1. Import and validate: same 422 `detail` for a bad body, the body is still read and validated
   before any table creation, the validation work still runs in the thread pool.
2. The new tests check what their names say and would fail on the matching regression.
3. Docs `src/app/web/pages.md` and `src/app/usecases/sources/onboarding.md` match.

Run only: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:warnings tests/unit/test_web_route_table.py tests/unit/test_web_source_onboarding_api.py tests/unit/test_web_app.py tests/unit/test_web_weekly_analytics.py tests/unit/test_web_home_page.py`

Report: findings first, each with file:line, severity, a concrete failing input and a fix; then
"no findings" for the checks that passed. Short.
