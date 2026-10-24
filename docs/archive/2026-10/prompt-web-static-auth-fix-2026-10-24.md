# Prompt: fix the /static/admin/ auth bypass in PR #110 (2026-10-24)

Executor: the background agent that finished PR #110 (coordinator `ai-parser-ba`). Same worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-wt-web-static`, branch `refactor/web-static-20261024`.
First `git checkout refactor/web-static-20261024` (the coordinator left the worktree on detached
bed1eb5, same commit) and `git status` must be clean.

## Bug (found by the coordinator in review)

With auth enabled and no session, `src/app/web/app.py` checks `path.startswith("/static/admin/")`
on the raw path, but StaticFiles normalizes the path itself. These return 200 with the admin JS:
`/static/css/../admin/core.js`, `/static//admin/core.js`, `/static/./admin/core.js`
(and `/static/ADMIN/core.js` on case-insensitive file systems such as macOS).
Only `/static/admin/core.js` returns 303. Probe: an ASGI call with a raw scope (TestClient/httpx may
normalize `..` before sending), see
`/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/ef9ee6d8-3194-45a0-9a65-7c1b58b42256/scratchpad/bypass.py`.

## Fix

1. In the auth middleware compute the check on a normalized path, the only change:
   ```python
   static_path = posixpath.normpath(path).lower()
   is_protected_ui = path == "/admin" or static_path.startswith("/static/admin/")
   ```
   (`import posixpath`; the comment one line above: normalized because StaticFiles resolves `..`,
   `//` and `.` itself; lower() for case-insensitive file systems.) Nothing else in the middleware.
2. Tests in `tests/unit/test_web_static_assets.py`: a parametrized test over the four bypass paths
   above, sent through a raw ASGI scope (like `bypass.py`), expecting not 200 (303 to `/login`)
   without a session; keep the existing tests.
3. `src/app/web/pages.md`: the rule about protected admin assets says the check runs on the
   normalized, lower-cased path and names the new test.
4. Checks: `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`
   (full suite), and run `bypass.py` again (all five lines must show 303).
5. Commit `fix(web): check /static/admin/ protection on the normalized path` with
   `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`, push to the same branch, wait for CI
   (`gh pr checks 110 --watch --interval 30`). Do not merge, do not tag. Do not run `rm -rf` on
   any tracked directory (the earlier `rm -rf build` deleted tracked files); use your scratch dir
   for build output.

## Report

New head SHA, CI result, `bypass.py` output after the fix, test results with exact commands.
