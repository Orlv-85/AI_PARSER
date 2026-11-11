# Review prompt: spec 020 T011 (common, signals and pages handlers call use cases)

You are a read-only reviewer. Do not edit files, commit, push or use the network. Do not spawn
sub-agents.

Worktree: /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-020-t011, branch
`refactor/020-t011-signals-pages`. The change is `git diff origin/master...HEAD`.

Context: `AGENTS.md`; `specs/020-web-through-usecases/spec.md` (FR-001, FR-003), `tasks.md`
(T011); `src/app/web/pages.md` (page views rules, code map), `src/app/usecases/daily/signals.md`
(flow line of the daily signals API).

The change is a refactor: no change for API answers, HTML pages, page view counting, stored data,
CLI or paid calls.

Check:
1. `web/routes/common.py`, `signals.py`, `pages.py`: every handler and helper keeps the same
   answers, status codes and error handling (which exceptions are caught where;
   `deps.create_all()` still inside the `try`; `_count_page` still swallows any error and logs;
   `_bulletin_response` still answers 503 HTML on storage errors).
2. Commits: `save_digest` commits before reading back; `count_page_view` commits; no read commits.
3. Rows are used after the session closes: digest groups and items (`selectinload` in
   `NewsDigestRepo.get_digest`; after `save_digest`'s commit too), bulletin rows, daily signal
   report and brief rows, daily stats. Find any lazy load or expired attribute that could raise
   DetachedInstanceError.
4. New use cases (`usecases/digest.py`, `page_views.py`, `collection_status.py`,
   `daily/signals_reads.py`, `news_reads.daily_stats`): correct, minimal, typed.
5. Tests: retargeted monkeypatches still hit a reader and still affect the paths they did before
   (note `digest_usecases.NewsDigestRepo` now also serves `/api/news/digests`); no assertion lost.
6. Docs match the code; no stale names.

Run only: `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-020-t011 && PYTHONPATH=src
/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:cacheprovider
tests/unit/test_layer_imports.py tests/unit/test_web_app.py tests/unit/test_web_weekly_analytics.py
tests/unit/test_web_public_digest.py tests/unit/test_web_home_page.py
tests/unit/test_web_digest_api.py tests/unit/test_monkeypatch_targets.py`

Report (short): findings ranked by severity, each with file:line, the failing scenario and a fix;
then "no findings" items you checked. No praise, no summary of the change.
