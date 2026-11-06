# Prompt (Codex, gpt-6.1-sol high, resume): spec 018 item 6b, review fixes (2026-11-06)

Same worktree and rules as your task (`prompt-item6b-home-page-codex-2026-11-06.md`): no commit,
push, gh, network, paid calls or sub-agents; `PYTHONPATH=src` on every pytest run. The coordinator
committed your work plus one doc fix (`period_view.py` is covered only by
`src/app/core/periodic/signals_period.md` again; do not add it back to `pages.md`'s `covers:`).

Review of PR #217 (Astra) asked for these changes. Doc first (`src/app/web/pages.md` Behavior and
Decisions), then a failing test for each, then code.

1. **Counting must not delay or block the page.** Count after the response is sent (FastAPI
   `BackgroundTasks` on `/` and `/daily`), and bound the counter's database wait: on PostgreSQL run
   `SET LOCAL lock_timeout = '1s'` and `SET LOCAL statement_timeout = '2s'` inside the counter's
   transaction before the upsert (skip on SQLite). Tests: the response is returned before the counter
   runs (e.g. a counter that raises or records order), and the PostgreSQL statements are issued
   (compile/inspect, like `test_page_views_increment_compiles_for_postgres`). A counter failure is
   still only logged.
2. **OpenAPI of `/` unchanged with the switch off.** The `date` query parameter of `/` must keep the
   same schema as on origin/master (`format: date`, same name, same optional default), while the
   switched-on home still answers a malformed date with 400 as decided. Choose the smallest way (e.g.
   `openapi_extra` or a schema override on the Query); add a test that compares the `/` parameter
   schema with `/daily`'s.
3. **CRAP of `build_pages_router` under 10.** Move the branching handler bodies out of the nested
   functions into module-level helpers (the nested functions only call them), without changing
   routes, names in the route table, responses or OpenAPI. Re-run crapper on `pages.py` and report
   the scores of `build_pages_router` and every new helper.

Not changed (decided by the coordinator, put in Decisions as "decided 2026-11-06 (agent)"): the page
keeps calling `deps.create_all()` as every other page does; `page_views` is created by it or by the
idempotent Alembic migration, whichever runs first after the deploy. Note it in `pages.md`.

Checks once at the end, in this order: full suite (`$E .../pytest -q -o addopts=`), `make lint`,
`python scripts/check_code_docs.py --diff origin/master --strict`, crapper on `pages.py` and
`page_views.py`, dryer 0.8 on them, mutator on each of them with the feature test files. After a fix
rerun only the check that failed.

Append a section "Review fixes" to `specs/018-daily-inference/records/report-item6b-home-page-2026-11-06.md`:
each fix, its test and how it failed first, check results with counts, CRAP scores, survivors.
