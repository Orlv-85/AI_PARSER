# Prompt: one honest bot user agent everywhere (2026-10-28)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. Implement with tests, open one
PR. Do not merge, do not tag. No production access needed.

## Owner decision (2026-10-28)

Option (b) of `docs/work/report-ua-options-2026-10-28.md` (read it): one honest bot user agent for
RSS/HTML fetch, archive capture, full-text/evidence download, robots.txt, and the source review
probe. Measured: no blocked host got worse; www.intel.com answers 403 to the Chrome string and 200
to a declared bot.

## What to do

- One constant, defined once and imported everywhere, e.g. in `src/app/ingest/fetcher.py`:
  `DEFAULT_USER_AGENT = f"ai-news-collector/{version} (+https://5kzt.l.time4vps.cloud/)"` where the
  version comes from the installed package metadata (`importlib.metadata.version("ai-news-collector")`,
  with a safe fallback) - check the real distribution name in `pyproject.toml`. If reading the
  version is awkward at import time, a fixed product token without version is fine; say which.
- Replace every other user agent: `Fetcher` users (`core/ingestion/pipeline/fetch.py`,
  `html_links.py`, `core/sources/validation.py`), `make_http_client` in
  `storage/article_evidence_cache.py` (archive, enrichment evidence, robots.txt), the review probe
  `core/sources/review.py`, and `scripts/sources_onboarding_helper.py` (it sends `Mozilla/5.0`).
  `git grep -n -i "user-agent\|user_agent\|Mozilla"` must show no other outgoing UA afterwards
  (tests and fixtures excepted).
- robots.txt: the downloader matches rules against the user agent; make it match our bot token
  (`ai-news-collector`), so `User-agent: ai-news-collector` rules and `*` rules apply to us.
- Do not change timeouts, retries, outage logic, `respect_robots` flags or anything readers see.
- Docs: the feature docs that name the user agent (`src/app/core/archive/capture.md`,
  `src/app/core/ingestion/pipeline.md`, `src/app/core/sources/onboarding.md` - check which do) and
  `docs/configuration.md` if it mentions it; one Decisions line ("declared bot instead of a browser
  string; decided by the owner 2026-10-28; measured ..."). Behavior rule with test names.
- Tests: the constant is the header of each client (Fetcher, evidence client, review probe); the
  robots matcher uses the bot token (a robots.txt that disallows `ai-news-collector` blocks us, one
  that disallows only `Googlebot` does not).

## Steps

1. `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b feat/honest-ua-20261028 ../AI_PARSER-wt-ua origin/master`. No git writes in the main folder.
2. Doc, tests, code. Checks: `make lint PYTHON=../AI_PARSER/venv1/bin/python`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts=""` (full; read the
   last line), `../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`, `bash -n` if a script changed.
3. Commit `feat(http): send one honest bot user agent everywhere` ending with
   `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push; `gh pr create --base master`, body
   ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final answer)

PR URL and SHA; the UA string; every place changed (file:line); the robots matching change; tests
(fail before / pass after); docs touched; full gate last line.
