# Prompt: move inline CSS/JS of the web pages into static files (2026-10-24)

You are the **executor**. Coordinator: session `ai-parser-ba` (it reviews your PR; the owner merges
code PRs only after the coordinator's review). Owner approved the plan on 2026-10-24.

Goal: a move-only refactor. What a visitor or an admin sees and does on the site must not change.
Inline `<style>` and `<script>` blocks of four pages move into files served from `/static/`.

## Rules

- Read `AGENTS.md` first (sections "Feature Docs Next To Code", "Validation", "Code Changes").
- Work only in a worktree; no git writes in the main folder `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`:
  ```
  cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q
  git worktree add -b refactor/web-static-20261024 ../AI_PARSER-wt-web-static origin/master
  cd ../AI_PARSER-wt-web-static
  ```
  Run checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/python ...` / `../AI_PARSER/venv1/bin/pytest`.
- Do not touch `weekly_analytics.html`, `weekly_analytics_reports.html` (weekly v2 is off; its fate
  is decided later), deploy files, Dockerfiles, `docker-compose*.yml`, `deploy/Caddyfile`.
- Moved text is copied **byte for byte** (keep indentation). No reformatting, no renames, no fixes
  inside moved code. If you see a bug, list it in the report, do not fix it.

## Pages and blocks (line numbers on origin/master 218eaa6 or later; re-check them)

| Page (route) | `<style>` | `<script>` | Placeholders |
| --- | --- | --- | --- |
| `src/app/web/digest.html` (`/`, public) | 7-335 | 404-762 | in script: `__REPORT_DATE_QUERY__`, `__DEFAULT_REPORT_DATE__` (lines ~415-416); others are in HTML |
| `src/app/web/index.html` (`/admin`, login required) | 7-174 | 454-1275 | none |
| `src/app/web/news_stats.html` (`/news-stats`, public) | 7-182 | 240-352 | only in HTML |
| `src/app/web/login.html` (`/login`, public) | 7-59 | 73-94 | none |

## Steps

1. Layout:
   ```
   src/app/web/static/css/digest.css, news_stats.css, login.css
   src/app/web/static/js/digest.js, news_stats.js, login.js
   src/app/web/static/admin/admin.css
   src/app/web/static/admin/<3-4 files>.js   (admin JS of index.html)
   ```
   File content = the lines strictly between the opening and closing tag, verbatim.
2. In each page replace the block with a tag at the **same position**:
   `<link rel="stylesheet" href="/static/css/<page>.css">` and `<script src="/static/js/<page>.js"></script>`
   (admin: `/static/admin/...`). No `defer`, no `async`, no `type="module"`: classic scripts in the
   same place keep the same execution order and the shared global scope.
3. `digest.html`: the two lines with `__REPORT_DATE_QUERY__` and `__DEFAULT_REPORT_DATE__`
   (`const initialDigestUrl = ...;`, `const defaultReportDate = ...;`) stay in a small inline
   `<script>` placed right before `<script src="/static/js/digest.js">`; `digest.js` holds every
   other line of the block in the original order. The renderer in `routes/pages.py` does not change.
4. Admin JS (`index.html`, ~820 lines) splits into 3-4 files by meaning (for example: shared helpers
   and page switching / news view and filters / sources and onboarding / update status and polling).
   Cut **only between top-level statements** (between functions, never inside one); keep the
   original order: concatenating the files in the order of their `<script>` tags must give exactly
   the original block. Put the top-level `const`/`let` declarations in the first file. Name the files
   by content and write the split in the code doc (step 8).
5. `src/app/web/app.py`: mount the folder:
   `api.mount("/static", <StaticFiles subclass>(directory=<web dir>/"static"), name="static")`.
   The subclass adds `Cache-Control: no-cache` to its responses (browsers revalidate by ETag, so a
   deploy never mixes new HTML with old JS). Keep the router order comment intact.
6. Auth middleware in `app.py`: `/static/admin/...` gets the same protection as `/admin`
   (`is_protected_ui = path == "/admin" or path.startswith("/static/admin/")`). Other `/static/`
   paths stay public, as now (they are neither `/api/` nor `/admin`). Do not change anything else
   in the middleware.
7. `pyproject.toml` `[tool.setuptools.package-data]` `"app.web"`: add the new files (globs such as
   `"static/css/*.css"`, `"static/js/*.js"`, `"static/admin/*.css"`, `"static/admin/*.js"`). Check
   that they really land in the wheel:
   ```
   ../AI_PARSER/venv1/bin/pip wheel . --no-deps -w <scratch dir> -q && unzip -l <scratch dir>/ai_news_collector-*.whl | grep static
   ```
8. Code doc `src/app/web/pages.md` (AGENTS.md "Feature Docs Next To Code"): header
   `<!-- code-doc` / `module: src/app/web/routes/pages.py` / `covers:` with `src/app/web/routes/pages.py`,
   `src/app/web/*.html`, `src/app/web/static/**` / `-->`. Sections Behavior (pages, routes, public vs
   login, placeholders and who fills them, static assets, no-cache, Mermaid of request -> page ->
   assets; each rule names its tests), Decisions (static files instead of inline; admin assets
   protected; no-cache; no framework/bundler), Invariants, Code map (which file holds what, admin JS
   split), Tests. The docstring of `routes/pages.py` names the doc. Register the doc in
   `docs/README.md` (code docs table), `README.md` and `src/app/README.md` like the other code docs.
   Run `../AI_PARSER/venv1/bin/python scripts/check_code_docs.py` if it has a CLI, and the pytest
   check of it.
9. Tests (new file `tests/unit/test_web_static_assets.py`, follow the style of `test_web_app.py` /
   `test_auth_stage1.py`):
   - each of the four pages references its assets, and each referenced asset returns 200 with
     `text/css` / `javascript` content type and `Cache-Control: no-cache`;
   - with auth enabled and no session: `/static/admin/<file>.js` does not return the file (redirect
     to `/login` like `/admin`); `/static/css/digest.css` and `/static/js/login.js` return 200;
     with a session the admin asset returns 200;
   - a move guard: for each page, the inline block on `origin/master` is not in the repo any more,
     so instead pin the result: the `<script>` and `<link>` tags of each page are listed in the test
     (exact paths), so a later edit that drops one fails.
   If an existing test asserts on text that moved into a static file, change it to read the asset
   (through the test client) and list every such change in the report.
10. Validation (from the worktree):
    - `../AI_PARSER/venv1/bin/python -m ruff check src tests`
    - `../AI_PARSER/venv1/bin/pytest tests/unit -q -k "web or auth or code_docs"` first, then the full gate:
      `make lint PYTHON=../AI_PARSER/venv1/bin/python` and `../AI_PARSER/venv1/bin/pytest`
      (PYTHONPATH=src). Report exact results; do not call scoped checks "all passed".
    - Live smoke: `PYTHONPATH=src AI_NEWS_DB_URL=sqlite:///<scratch>/smoke.db ../AI_PARSER/venv1/bin/uvicorn app.web.app:app --port 8011`
      (check `scripts/run_web.sh` / `docs/configuration.md` for the right env names), then `curl -s
      localhost:8011/ | grep static`, `curl -sI localhost:8011/static/js/digest.js`, and the same for
      `/news-stats`, `/login`. Stop the server after.
11. Move check you run yourself and paste into the report: a short Python script that, for each page,
    takes the inline blocks from `git show origin/master:src/app/web/<page>.html` and compares them with
    the new files (concatenated in tag order; for digest, inline two lines + `digest.js` equal the
    original block as a multiset of lines and `digest.js` equals the original minus those two lines).
    Output must say `identical` for every block.
12. Commit (one commit is fine), message:
    ```
    refactor(web): move inline CSS/JS of four pages into static files (move-only)

    digest, admin (index.html), news_stats and login load their styles and scripts from
    /static/ (no-cache); admin assets need a session like /admin. Weekly pages unchanged.
    Code doc src/app/web/pages.md.

    Co-Authored-By: <your model line>
    ```
    Then `git push -u origin refactor/web-static-20261024` and
    `gh pr create --base master --title "refactor(web): move inline CSS/JS into static files (move-only)" --body "<summary, move-check output, test results, what was not run>"`.
    Do not merge. Do not tag.

## Report (send to `ai-parser-ba` with SendMessage, and paste in your final answer)

- PR URL and head SHA;
- list of new files with line counts; how the admin JS was split (file -> functions);
- move-check output (step 11);
- tests changed (if any) and why;
- wheel listing of `static/`;
- lint/tests results with exact commands, the live smoke output;
- anything you noticed but did not fix; open questions.
