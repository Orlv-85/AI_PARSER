# Prompt: do not give article full text to anonymous API callers (2026-10-23)

You are the implementer for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. Read `AGENTS.md` first and
follow it. Work only in the worktree below; do not write to git in the main folder. Do not merge,
tag or touch prod.

## Facts

- `GET /api/news/links` is public when auth is on (`src/app/web/app.py`, `auth_middleware`,
  `is_public_news_api`). With `include_content=true` it returns `summary` and up to 12000 chars of
  `content` per article (`src/app/web/routes/news.py`, `list_news_links`). Anyone can read the
  stored third-party full text; spec 016 (`specs/016-article-archive/`) says full text is internal
  only and never republished.
- There is no MCP server any more (removed earlier; its deploy vars removed in PR #78).
- `scripts/digest_generator.py` (legacy weekly job, `scripts/run_weekly_analytics_job.sh`) calls
  `GET /api/news/links?...&include_content=true` and sends `Authorization: Bearer <token>`
  (`AINEWS_PUBLISH_API_TOKEN`, see `docs/configuration.md`). It must keep working.
- The web page `/` does not ask for `include_content` (check the templates/static JS to confirm).

## Owner decision 2026-10-23

Close `include_content` for anonymous callers.

## Decided by the coordinator (implement as written)

- With auth enabled, `include_content=true` on `GET /api/news/links` returns the content fields only
  to a caller with a valid session cookie or a valid publish bearer token
  (`verify_bearer_token(..., settings.publish_api_token)`). Anyone else gets the normal response
  WITHOUT `summary`, `content` and `rank_score` (as if `include_content=false`), status 200; no
  error, so old clients do not break. With auth disabled (local dev) nothing changes.
- Same rule for any other public GET endpoint that can return `content` (check
  `/api/news/digests`, `/api/news/daily-signals`, `/api/news/weekly-analytics*`,
  `/api/news/stats/daily`; list in the report which return article text and how you handled them).
- Implement it in one place (a request flag set by the middleware, e.g. `request.state`, read by
  the route) rather than duplicating cookie/token checks in routes. Keep the publish token's POST
  scope unchanged.

## Setup

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-wt-public-fulltext -b fix/close-public-fulltext-20261023 origin/master
cd ../AI_PARSER-wt-public-fulltext
```

If the branch or the worktree already exists, stop and report instead of reusing it.
Checks in the worktree: `PYTHONPATH=src ../AI_PARSER/venv1/bin/python ...`,
`PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest ...`.

## Steps

1. Docs: the web code has no code doc yet. Add the rule to `docs/configuration.md` next to the
   publish token text (who gets `include_content`), and to `docs/troubleshooting.md` only if a
   non-obvious failure comes up. Do not create a new code doc for the whole web app in this PR.
2. Code as decided above.
3. Tests (find the existing auth tests, e.g. `grep -rn "is_public_news_api\|include_content" tests`):
   - `test_anonymous_links_never_get_content`: auth on, no cookie, `include_content=true` -> 200,
     items have no `content`/`summary`/`rank_score`.
   - `test_logged_in_links_get_content`: valid session cookie -> content present.
   - `test_publish_token_links_get_content`: valid bearer token -> content present; invalid token ->
     no content.
   - `test_auth_disabled_links_content_unchanged`.
   - one test per other endpoint you changed.
4. Checks (all must pass, files ASCII):
   ```
   PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests/unit -k "auth or news or links"
   PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py --diff origin/master --strict
   make lint PYTHON=../AI_PARSER/venv1/bin/python
   PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest
   ```
5. Commit, push, PR:
   ```
   git add -A
   git commit -m "fix(web): keep article full text from anonymous API callers" -m "GET /api/news/links?include_content=true returned up to 12000 chars of stored third-party text to anyone. Content fields now go only to a logged-in session or the publish bearer token (digest_generator); anonymous callers get the same response without them." -m "Co-Authored-By: <your model name> <noreply@anthropic.com>"
   git push -u origin fix/close-public-fulltext-20261023
   gh pr create --base master --head fix/close-public-fulltext-20261023 \
     --title "fix(web): keep article full text from anonymous API callers" \
     --body "Owner decision 2026-10-23. With auth on, include_content returns summary/content/rank_score only to a valid session or the publish bearer token; anonymous callers get the response without them (200, no error). Auth off unchanged. digest_generator keeps working (bearer). Gate: make lint + full pytest (paste results)."
   ```
   Use your real model name in Co-Authored-By, or drop the line.

## Report (all fields required)

- PR link; branch; commit SHA; `git diff --stat origin/master`.
- Output tail of each check in step 4.
- Which public endpoints return article text and what changed for each.
- Deviations and why; open questions, one line each (AGENTS.md "Owner And Questions").
