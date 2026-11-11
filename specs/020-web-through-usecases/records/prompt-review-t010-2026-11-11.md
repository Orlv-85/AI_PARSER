# Review prompt: spec 020 T010 (bulletin, news and period handlers call read use cases)

You are a read-only reviewer. Do not edit files, commit, push or use the network. Do not spawn
sub-agents.

Worktree: /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-020-t010, branch
`refactor/020-t010-web-reads`. The change is `git diff origin/master...HEAD`.

Context: `AGENTS.md`; `specs/020-web-through-usecases/spec.md` (FR-001, SC-002), `tasks.md`
(T010); `src/app/storage/bulletin_store.md` and `src/app/core/periodic/signals_period.md` (code
map rows of the new use case files).

The change is a refactor: no change for API answers, HTML pages, stored data, CLI or paid calls.

Check:
1. `web/routes/bulletin.py`, `news.py`, `period.py`: every handler and helper (`latest_week`,
   `has_month`, `_read_page`) keeps the same answers, status codes, error handling (which
   exceptions are caught where; `deps.create_all()` still inside the `try`) and the same reads.
   `_read_page` still reads index, report and brief in one session; its `explicit`/`start` cases
   map to `period_page(..., latest=not explicit)` with the same result.
2. Rows are now used after the session closes (no commit happens, so nothing is expired): find
   any attribute read after close that was read inside the session before and could lazy-load
   (relationships, deferred columns) and fail with DetachedInstanceError.
3. `usecases/news_reads.py`, `usecases/bulletin/stored.py`, `usecases/periodic/period_reads.py`:
   correct, minimal, typed; `SHOWN_STATUSES` keeps the old `_SHOWN` value and comment.
4. Tests: retargeted monkeypatches (`news_reads.ArticleRepo`,
   `app.usecases.periodic.period_reads.PeriodSignalRepo.index`) still hit a reader; the
   provider-code test now also scans `period_reads`; no assertion lost.
5. Docs match the code; no stale names.

Run only: `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER-020-t010 && PYTHONPATH=src
/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -p no:cacheprovider
tests/unit/test_layer_imports.py tests/unit/test_web_app.py tests/unit/test_web_digest_api.py
tests/unit/test_web_period_page.py tests/unit/test_web_period_signals_api.py
tests/unit/test_monkeypatch_targets.py tests/unit/test_auth_stage1.py`

Report (short): findings ranked by severity, each with file:line, the failing scenario and a fix;
then "no findings" items you checked. No praise, no summary of the change.
