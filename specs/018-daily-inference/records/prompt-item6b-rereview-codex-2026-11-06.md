# Prompt (Codex, gpt-6-astra high): re-review of PR #217 fixes, item 6b (2026-11-06)

Repo `ai-news-collector`, worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item6b-home-page`, branch
`feat/018-item6b-home-page`. Read-only: no edits, commits, push, gh, network or sub-agents.

Your earlier review: `specs/018-daily-inference/records/review-item6b-codex-2026-11-06.md`. Fix task:
`specs/018-daily-inference/records/prompt-item6b-fixes-codex-2026-11-06.md`; executor notes: section
"Review fixes" of `specs/018-daily-inference/records/report-item6b-home-page-2026-11-06.md`.
Review only `git diff ec23c6f..HEAD -- src tests` plus `src/app/web/pages.md`.

Check: (1) the counter now runs after the response body is sent, a failing or slow counter cannot
change or delay the response, the PostgreSQL `SET LOCAL` timeouts are in the same transaction as the
upsert and the session is always closed; (2) the `/` OpenAPI parameter equals origin/master's and the
switched-on home still answers a malformed date with 400; (3) the handler extraction changed no
route, name, order, response, status code, cookie or auth behaviour (login/logout/stats/collection
status); (4) new tests are honest; anything you flagged before still open.

Run only: `env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_web_home_page.py tests/unit/test_page_views.py tests/unit/test_web_route_table.py tests/unit/test_web_auth.py`
(drop a file that does not exist).

Final message: verdict (approve / changes needed), findings with file:line and a concrete scenario,
minor notes separately. Short.
