# Prompt: Fix unauthenticated POST on public news API (2026-10-18)

You are fixing a production security bug in `ai-news-collector`
(repo `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`, Python 3.14, FastAPI). Production site:
https://5kzt.l.time4vps.cloud/

## Work in a separate worktree (mandatory)

Another feature branch (`feat/006-daily-ai-signals`) is checked out in the main folder and must not be
disturbed. Create your own worktree from `master`:

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-authfix -b fix/public-post-auth-20261018 origin/master
cd ../AI_PARSER-authfix
```

Use `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python` and `.../venv1/bin/pytest`
(or create a venv in the worktree if imports resolve to the wrong tree; state what you did).

## Read first

- `AGENTS.md`, `docs/troubleshooting.md`
- `.specify/specs/004-daily-digest-public-admin/spec.md` (public digest + external agent submission;
  it defines who is allowed to POST digests)
- `src/app/web/app.py` - `auth_middleware` (around line 400), `save_news_digest`
  (`POST /api/news/digests`), `save_weekly_ai_analytics` (`POST /api/news/weekly-analytics`)
- `src/app/web/auth.py`, `src/app/config/settings.py` (auth settings; note the existing
  `mcp_auth_token` pattern and its validation)
- `scripts/digest_generator.py` (`read_json_response`, `publish_digest`, weekly publish path) and
  `scripts/run_weekly_analytics_job.sh` - these POST to the endpoints over HTTP
- Tests: `tests/unit/test_digest_generator.py`, `tests/unit/test_deepseek_digest.py`, web auth tests
  (`grep -rln "auth" tests/unit | head`)
- `deploy/`, `docker-compose.prod.yml`, `docs/configuration.md`, `docs/deploy.md`, README operator notes

## The bug (confirmed on production by the coordinator, 2026-10-18)

`is_public_news_api` in `auth_middleware` is a path-only allowlist, not method-aware. It contains
`/api/news/digests` and `/api/news/weekly-analytics`, which also serve POST handlers that write data.
Probe with an empty JSON body:

```text
POST /api/news/digests          -> 422  (passed auth, failed validation)
POST /api/news/weekly-analytics -> 422
POST /api/update/run            -> 401  (control: protected)
```

So anyone on the internet can overwrite any day's public digest or weekly report.

## Goal

Write methods on public paths require authentication; public reads keep working unchanged; the
legitimate machine caller (`scripts/digest_generator.py` and any job that uses it) keeps working.

## Requirements

1. Make the public allowlist method-aware: only `GET` (and `HEAD`/`OPTIONS` if needed) are public for
   the listed paths. Any other method on any `/api/` path requires auth. Prefer a general rule over
   enumerating the two POST endpoints, so future write handlers on public paths are protected by
   default.
2. Accepted credentials for writes: a valid admin session cookie (existing), or a machine token sent as
   `Authorization: Bearer <token>`. Follow the `mcp_auth_token` pattern: a new setting (e.g.
   `AINEWS_PUBLISH_API_TOKEN` / `publish_api_token`), minimum length validation, constant-time
   comparison (`hmac.compare_digest`), never logged. Decide whether the token is accepted only for the
   two publish endpoints or for all protected API; justify (least privilege preferred).
3. When auth is disabled entirely (`auth_enabled` false, local dev), behaviour stays as today.
4. `scripts/digest_generator.py`: send the bearer token from an env var when set, for every POST it
   makes to the app; clear error message on 401. Update `scripts/run_weekly_analytics_job.sh` only if it
   needs to pass the env through.
5. Find every production caller of these POST endpoints (timers, cron, scripts, docs, external agent
   notes) and list them in your report. Check whether the weekly HTTP publish job is actually scheduled
   in production; if you cannot determine it, say so.
6. Deploy config: add the token env var to `docker-compose.prod.yml` env enumeration (empty default)
   and document it in `docs/configuration.md` and README. Do not change ports, other auth settings,
   cookie settings, retention or DB behavior. Do not deploy.
7. Tests (write first, see them fail, then fix):
   - unauthenticated POST to both endpoints -> 401; GET on both stays 200 without auth;
   - POST with valid session cookie -> accepted; with valid bearer token -> accepted; wrong/short token
     -> 401;
   - a generic check: every route with a non-GET method under `/api/` is rejected without credentials
     when auth is enabled (iterate `app.routes`), except the explicit auth routes (`/api/auth/login`,
     `/api/auth/logout`);
   - auth disabled -> unchanged behaviour;
   - `digest_generator` sends the header when the env var is set.
8. Add a case to `docs/troubleshooting.md` (symptom, cause, fix) per AGENTS.md.

## Validation

- Scoped: `ruff check src tests scripts`, pytest on the touched test files.
- Before commit: `make lint PYTHON=<venv python>` and full `pytest`. Report exactly what ran.
- `bash -n` for any changed shell script.

## Delivery

- Commit on `fix/public-post-auth-20261018`, push the branch and open a PR to `master` (security fix;
  the owner approved doing this as a separate task). Do not merge, do not deploy.
- In the PR description and your reply: what changed, why, test evidence, the list of callers, and the
  exact **operator steps for rollout**, in order, so nothing breaks:
  1. generate a token (command), 2. add it to the server `.env`, 3. configure every machine caller,
  4. deploy, 5. verify with the same empty-body probe that POST now returns 401 and that GET pages still
  load, 6. verify the next scheduled publish still succeeds.
- Note: after deploy, check that production digests for recent days were not tampered with (compare a
  few days against expectations / logs) and report how to check this; do not modify data.
- When done, remove nothing in the main folder; leave the worktree in place and mention its path.
