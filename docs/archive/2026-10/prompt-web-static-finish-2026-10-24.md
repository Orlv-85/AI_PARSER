# Prompt: finish the web static split (2026-10-24)

You are a background executor for coordinator `ai-parser-ba`. The task is defined in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-web-static-split-2026-10-24.md`
(read it fully; its rules apply). Another session did steps 1-9 and stopped; do NOT start over.

## State you take over

- Worktree `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-wt-web-static`, branch
  `refactor/web-static-20261024` off origin/master 173240e, all changes uncommitted.
- 11 files under `src/app/web/static/` (`css/`, `js/`, `admin/`: `admin.css`, `core.js`,
  `updates.js`, `news.js`, `sources.js`), `_NoCacheStaticFiles` mount and `/static/admin/`
  protection in `app.py`, package-data globs, doc `src/app/web/pages.md` (registered), new
  `tests/unit/test_web_static_assets.py` and `tests/unit/conftest.py`, 11 existing tests repointed
  at the assets, stale refs fixed in `signals.md` and `onboarding.md`.
- Reported done: move check identical, ruff clean, `make lint` passes, check_code_docs ok, scoped
  web/auth tests pass. NOT done: full pytest, live smoke, commit/push/PR.

Work only inside that worktree. No git writes in the main folder. Checks:
`cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-wt-web-static` then
`PYTHONPATH=src ../AI_PARSER/venv1/bin/...`.

## Steps

1. `git status --short` and `git diff --stat`; confirm the state above. Do not touch weekly pages,
   deploy files, Dockerfiles, Caddyfile.
2. Re-run the move check yourself (step 11 of the task prompt): a Python script comparing every
   inline `<style>`/`<script>` block of `git show origin/master:src/app/web/<page>.html` (digest,
   index, news_stats, login) with the new files (admin: core, updates, news, sources concatenated
   in `<script>` tag order equal the original block byte for byte; digest: the two placeholder lines
   inline + `digest.js` = original block). Also check that the markup outside the blocks is
   unchanged. Save the script in your scratch dir, paste its output.
3. `pages.md`, section Decisions: add one line (coordinator decision 2026-10-24): "Admin JS is four
   classic scripts; an exception in one file no longer stops the files after it (before, one inline
   block stopped as a whole). Accepted: affects only error cases." Also in Behavior, if not there,
   state that the admin event wiring lives in `sources.js` because it uses functions of all files.
4. Full gate: `make lint PYTHON=../AI_PARSER/venv1/bin/python` and
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest` (the whole suite, e2e included). If something fails,
   read `docs/troubleshooting.md` first; fix only what this change broke; report the rest.
5. Live smoke (step 10 of the task prompt): start uvicorn on port 8011 with a scratch SQLite DB
   (env names from `scripts/run_web.sh` / `docs/configuration.md`), `curl` `/`, `/news-stats`,
   `/login`, one asset of each page with `-I` (expect 200, `Cache-Control: no-cache`), and
   `/static/admin/core.js` with auth enabled and no session (expect a redirect to `/login`) if auth
   can be enabled locally with env vars; otherwise say so. Stop the server.
6. Commit with the message from step 12 of the task prompt; end it with
   `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`. Push, then
   `gh pr create --base master --title "refactor(web): move inline CSS/JS into static files (move-only)" --body "..."`
   with: summary, move-check output, admin split (file -> original line ranges), tests changed,
   results of lint/tests/smoke, what was not run. End the body with
   `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Do not merge, do not tag.
7. Wait for CI (`gh pr checks <N> --watch --interval 30`) and report its result. If CI fails, read
   the log (`gh run view <id> --log-failed`), fix and push once more; do not say a CI failure is
   "local only" without proof.

## Report (your final answer)

PR URL, head SHA, CI result, move-check output, full gate results with exact commands, smoke
output, files changed outside `src/app/web` and why, anything not done.
