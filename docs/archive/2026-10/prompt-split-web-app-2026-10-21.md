# Prompt: split `web/app.py` into routers (2026-10-21)

Repository `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (Python 3.14, `ai-news-collector`).
Read `AGENTS.md` first. Work in a separate git worktree from `origin/master`; other sessions may
work in the main folder. `venv1` is installed editable on the main folder: in the worktree run
checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/...` (adjust the relative path).

## Context

Step 3 of `docs/plan-split-overloaded-modules-2026-10-21.md` (read its "General rules" and
section 3). `src/app/web/app.py` (~1370 lines) has one `create_app` with the auth middleware and
~39 route closures for six areas, plus ~320 lines of module-level render/response builders. Split
it by moving code only: same routes, same responses, same auth, same order.

## Design (decided by the coordinator)

- `web/routes/{pages,news,signals,weekly,updates,sources}.py`. Each exposes
  `build_<area>_router(deps) -> APIRouter`; `deps` is one small frozen dataclass in
  `web/routes/__init__.py` (or `web/deps.py`) holding what the closures capture today
  (`settings`, `settings_store`, `update_service`, `source_intake`, `SessionLocal`, `create_all`,
  the signer, ...). Read the closures to get the exact list; no new behavior in it.
- `create_app` builds the shared objects, adds the middleware (stays in `app.py`) and includes the
  routers so the final route table has the same order as today. Fixed paths must still be
  registered before parameter paths that could match them (e.g. `/api/news/export`,
  `/api/news/links`, `/api/news/digests` before `/api/news/{article_id}`).
- Render and response builders move with the routes that use them; shared ones go to one helper
  module. HTML files and `package-data` stay as they are.
- `app.web.app.create_app` and the module-level `app` stay importable (tests, `ai-news serve`,
  `run_web.sh`).

## Rules

- First commit, before any move: a test that dumps the route table of `create_app()` (method,
  path, name, response model, order) and the set of routes the auth middleware protects, and pins
  them. It must pass before and after.
- Monkeypatching: `tests/unit/test_web_app.py` and others call
  `monkeypatch.setattr(web_app_module, "ArticleRepo" / "NewsDigestRepo" / "SessionLocal" / ...)`.
  After the move those names are looked up in the router modules, so these patches would silently
  stop applying. List every `setattr` on `app.web.app` and every quoted `"app.web.app.` string, and
  re-point each to the module where the code now looks the name up. Show the list in the PR.
- No logic edits, no renamed endpoints or functions, no response changes. Keep code ASCII.
- No code doc is required for `web/` in this PR (several features); if a feature doc's `covers:`
  names `web/app.py` or `web/signals_view.py`, keep it valid (`core/daily/signals.md` covers
  `web/signals_view.py`).

## Checks

- Full gate: `make lint PYTHON=...`, full `pytest` (same pass count as `origin/master` plus the new
  pin test), `scripts/check_code_docs.py` and `--diff origin/master --strict`.
- Smoke: `ai-news serve` locally with auth on and with auth off; `/`, `/health`, `/admin` (redirect
  or 401 without login), `/api/news`, `/api/news/digests`, `/api/news/daily-signals` answer as on
  master. Compare responses of these paths against a master build of the same local DB.
- Package build like Docker: `pip wheel --no-deps`; `app/web/routes/*` and the HTML files are in
  the wheel.

## Output

- One PR, do not merge. In your reply: the PR link; new module sizes; the `deps` fields; the
  monkeypatch re-pointing list; the route-table pin result; exact checks with pass counts; open
  questions one line each (how settled, or a yes/no question for the owner with a recommendation,
  only if it changes what readers see or what is paid).
- Save any prompt you write for another session to a file per `AGENTS.md`.
