# Prompt (Codex fix round, gpt-6.1-sol high): spec 018 item 4c review findings (2026-11-02)

Same worktree and branch as your item 4c work:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page`. Do not commit,
push or use gh. No network, no paid calls. Do not spawn a doc review or any sub-agent.
Review report: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/tasks/item4c-preview-page.review-20261102-142140.md`.

Fix exactly these, behavior unchanged (existing tests stay green, no test changes needed except
imports):

1. `build_pages_router` complexity rose 21 -> 25 with the `/bulletin` route. Move the lookup,
   rendering and `SQLAlchemyError` handling into a module-level function (for example
   `_bulletin_response(deps, target_date) -> HTMLResponse` in `src/app/web/routes/pages.py`), and
   leave the route as a one-line wrapper. `build_pages_router` must be back at complexity 21.
2. Rename `_parse_day` in `src/app/web/routes/bulletin.py` to public `parse_day` and update both
   callers. If `pages.md` or `bulletin_store.md` names it, update the doc in the same change.

Checks: while working run only `tests/unit/test_web_bulletin_page.py tests/unit/test_web_route_table.py
tests/unit/test_bulletin_store.py` and ruff. Once at the end: `PYTHONPATH=src make lint
PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`, full
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" -n auto`,
`env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 ~/tools/unclebob/crapper/crapper src/app/web/routes/pages.py src/app/web/routes/bulletin.py`
(report `build_pages_router` and the new helper), and last, alone,
`PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python scripts/check_code_docs.py --diff origin/master --strict; echo exit=$?`.
Report: what changed (file:line), each check's result line and exit code.
