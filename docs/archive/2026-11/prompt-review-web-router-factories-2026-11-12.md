# Review: web router factories (branch refactor/web-router-factories, commit 7f06b60)

Read-only review. Do not edit files, commit, push or use gh; no network. Do not spawn sub-agents.

Change: handler bodies of `build_sources_router` (`src/app/web/routes/sources.py`),
`build_news_router` / `build_news_article_router` (`news.py`) and `build_weekly_router`
(`weekly.py`) moved to module-level functions taking `deps`; `_http_errors` moved from
`sources.py` to `src/app/web/routes/common.py` and replaces the try/except blocks of news and
weekly. `src/app/web/app.py`: `create_app` split into `_onboarding_engine`, `_signer`,
`_auth_middleware`, with the path rule in `_requires_auth` / `_is_allowed`. Intended: no behavior
change. Old code: `git show HEAD~1:<path>`.

Check, with concrete inputs:
1. Auth parity: for every (method, path, session yes/no, bearer token yes/no, auth on/off) the new
   middleware lets through, returns 401 JSON or redirects to `/login` exactly as the old
   `auth_middleware`; `request.state.full_text_allowed` is the same; `session_expired` is logged in
   the same cases. Note the token is now verified once, eagerly.
2. Router parity: status codes, error `detail`, response bodies, the order of
   `create_all` / `create_onboarding_tables` versus the error mapping (a storage error in table
   creation is still 503; a `ValueError` maps to the same status as before per route), the
   validate route still runs the blocking work in the thread pool, endpoint names unchanged.
3. weekly: `_item_payloads` filters exactly as the old nested `_serialize_items`; save maps
   `ValueError` to 409.
4. Docs: `src/app/web/pages.md` and `src/app/usecases/sources/onboarding.md` match the code.

Run only: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:warnings tests/unit/test_web_route_table.py tests/unit/test_web_app.py tests/unit/test_web_source_onboarding_api.py tests/unit/test_web_weekly_analytics.py tests/unit/test_public_api_write_auth.py tests/unit/test_auth_stage1.py`

Report: findings first, each with file:line, severity, a concrete failing input and a fix; then
"no findings" for the checks that passed. Short.
