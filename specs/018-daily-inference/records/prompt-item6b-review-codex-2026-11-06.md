# Prompt (Codex, gpt-6-astra high): review of PR #217, spec 018 item 6b (2026-11-06)

Repo `ai-news-collector`, worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item6b-home-page`, branch
`feat/018-item6b-home-page` (one commit on origin/master). Read-only review: do not edit code, do
not commit, push or use gh; no network; no sub-agents.

Task: `specs/018-daily-inference/records/prompt-item6b-home-page-codex-2026-11-06.md` (decisions
1-9 are the contract). Executor report: `specs/018-daily-inference/records/report-item6b-home-page-2026-11-06.md`.
Review `git diff origin/master...HEAD` and the doc `src/app/web/pages.md`.

Focus, in this order:

1. Switch off (production now): is `/` exactly the old digest for every input (no date, valid date,
   bad date, storage error, auth on/off), and are the APIs, `/weekly`, `/monthly` and `/bulletin`
   unchanged except the intended `/daily` links? Any change of status codes or OpenAPI that a
   client could notice?
2. Switch on: decisions 2, 4, 5, 6 of the prompt. Escaping and http/https-only links still hold on
   the home render; no checking data (`text_origin`, `origin`, numbers, reason codes) leaks to `/`.
3. Page counter: the upsert is atomic on PostgreSQL and SQLite; the migration chain has one head and
   matches the model; a counter failure (missing table, locked DB, PostgreSQL error) never changes
   the response and leaves no broken session; nothing about the visitor is stored; does a write on
   every GET to `/` add a risk (a slow or failing DB write on the public page, one transaction per
   request)? Is `deps.create_all()` behaviour consistent with how other tables reach production
   (Alembic at deploy)?
4. Compose forwards `AINEWS_BULLETIN_HOME_PAGE` with default false.
5. Tests honest (not implementation-bound); doc Behavior matches the code; test names real. The
   executor changed existing tests (listed in its report): is each change necessary?
6. CRAP: `build_pages_router` scores 32.9 (nested route functions); say whether this change made
   it worse and whether a small extraction is warranted now (owner rule: functions touched by a real
   task go under CRAP 10).

Run only: `env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= tests/unit/test_web_home_page.py tests/unit/test_page_views.py tests/unit/test_web_bulletin_page.py tests/unit/test_web_period_page.py tests/unit/test_web_route_table.py`.

Answer in your final message (the sandbox may not let you write files): verdict (approve / changes
needed), findings ranked by severity with file:line and a concrete failing scenario, then minor
notes separately. Keep it short.
