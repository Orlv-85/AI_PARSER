# Troubleshooting

Known failures with confirmed causes and fixes. Agents: check this file before
debugging a failing test, CI run, or runtime error, and add a case here when you
resolve a new one (keep entries in English, valid JSON, newest last).

Basic setup problems (`ModuleNotFoundError`, missing `data/`, empty `top`) are in
the Troubleshooting section of `README.md`.

## Case registry

```json
{
  "cases": [
    {
      "id": "flaky-e2e-update-and-read-news",
      "date": "2026-10-17",
      "area": "tests/e2e",
      "symptom": "tests/e2e/test_api_e2e.py::test_api_e2e_update_and_read_news fails intermittently in CI with `assert terminal is not None` (tests/e2e/test_api_e2e.py:80). Other tests pass; a rerun of the failed job passes.",
      "evidence": [
        "GitHub Actions runs 39024218187 (PR #34) and 39026191381 (PR #35) failed, then passed on rerun",
        "The PRs did not touch the update pipeline or web code"
      ],
      "cause": "Timing, not a race. The test polled GET /api/update/status 50 x 0.02s (~1s). UpdateRunService runs the fetch cycle in a background thread (default update_execution_mode=thread); on a loaded runner it can exceed that window. Failures inside the job end as status 'failed', never a stuck 'running'.",
      "fix": "Poll with a 15s deadline (time.monotonic) and a 0.05s sleep; assertions unchanged. PR #36.",
      "verification": "21 consecutive local passes in a clean copy without .env; CI passed on first attempt. Not verified under CPU load.",
      "if_it_recurs": "If `terminal is not None` fails again with the 15s deadline, it is not timing: inspect UpdateRunService._run and the 'update_run_failed' log entry (src/app/web/service.py)."
    },
    {
      "id": "local-e2e-auth-settings-validation",
      "date": "2026-10-17",
      "area": "local test runs",
      "symptom": "Tests that build the app fail locally with pydantic ValidationError: 'Authentication is enabled, missing required auth settings: AINEWS_AUTH_USERNAME, AINEWS_AUTH_PASSWORD_HASH'. CI does not fail.",
      "cause": "The local .env enables auth or sets auth values, and Settings validation requires the full auth set. Exporting AINEWS_AUTH_ENABLED=false is not enough because other auth values are still read.",
      "fix": "Run the suite in a clean copy without .env (rsync the repo excluding .env, venv1 and .git, then run with PYTHONPATH=src), as CI does.",
      "verification": "tests/e2e/test_api_e2e.py passes in such a copy."
    },
    {
      "id": "public-api-post-auth-bypass",
      "date": "2026-10-18",
      "area": "src/app/web/app.py auth_middleware",
      "symptom": "With auth enabled, an empty-body POST to /api/news/digests or /api/news/weekly-analytics returned 422 (validation) instead of 401, so anyone could overwrite a public digest or weekly report. After the fix, digest_generator.py publish commands fail with 'Unauthorized POST ... AINEWS_PUBLISH_API_TOKEN is not set' (or 'was rejected').",
      "cause": "is_public_news_api was a path-only allowlist; the same paths also serve POST handlers that write data. Publishers now need credentials.",
      "fix": "The allowlist is public for GET/HEAD only; other methods on /api/ require a session cookie, or AINEWS_PUBLISH_API_TOKEN as 'Authorization: Bearer <token>' for POST to the two publish paths. In production the token comes from the AINEWS_PUBLISH_API_TOKEN repository secret (deploy workflows write it to .env); give the publisher the same value.",
      "verification": "tests/unit/test_public_api_write_auth.py; production probe: curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' https://<host>/api/news/digests returns 401."
    },
    {
      "id": "sqlalchemy-dict-over-result",
      "date": "2026-10-18",
      "area": "storage (SQLAlchemy 2.1)",
      "symptom": "TypeError: 'ChunkedIteratorResult' object is not subscriptable from dict(session.execute(select(a, b)).tuples()); also SADeprecationWarning: The Result.tuples() method is deprecated.",
      "cause": "A Result has a keys() method, so dict() treats it as a mapping and subscripts it instead of iterating rows. Result.tuples() is deprecated in SQLAlchemy 2.1 (rows already behave like tuples).",
      "fix": "Materialize the rows first: dict(session.execute(stmt).all()); iterate the Result directly elsewhere; do not call .tuples().",
      "verification": "tests/unit/test_daily_signals_repo.py passes with -W error::DeprecationWarning."
    },
    {
      "id": "alembic-only-db-has-no-digest-tables",
      "date": "2026-10-18",
      "area": "migrations / tests",
      "symptom": "A migration test that upgrades a fresh SQLite file with `alembic upgrade` and then writes NewsDigestReport fails with 'no such table: news_digest_reports'.",
      "cause": "The digest tables (news_digest_reports/groups/items) have no Alembic migration; they are created by create_all() when the app or CLI starts. A database built only by Alembic lacks them.",
      "fix": "In migration tests, use tables that migrations create (e.g. articles) for pre-feature rows, or call Base.metadata.create_all() before writing digests.",
      "verification": "tests/unit/test_daily_signals_migration.py passes."
    },
    {
      "id": "alembic-env-disables-loggers",
      "date": "2026-10-18",
      "area": "tests (caplog)",
      "symptom": "Full suite: tests/unit/test_mcp_server.py and test_ingest_rss_additional.py fail with empty caplog.text, but pass when run alone.",
      "cause": "A test that runs `alembic command.upgrade` executes src/app/storage/migrations/env.py, whose logging.config.fileConfig(alembic.ini) disables all existing loggers. Every test collected after it loses log capture. test_weekly_storage.py does the same but sorts after the affected files.",
      "fix": "In migration tests, monkeypatch logging.config.fileConfig to a no-op before calling alembic commands.",
      "verification": "Full ./venv1/bin/pytest passes with tests/unit/test_daily_signals_migration.py collected before test_mcp_server.py."
    },
    {
      "id": "local-suite-skips-postgres-integration",
      "date": "2026-10-18",
      "area": "tests/integration, CI",
      "symptom": "Local ./venv1/bin/pytest is green with '9 skipped', but CI fails in tests/integration/test_legacy_cleanup_postgres.py, e.g. 'ValueError: Unknown article FK dependency: article_signals'.",
      "evidence": ["GitHub Actions run 39145455108 (branch feat/006-daily-ai-signals)"],
      "cause": "The PostgreSQL integration tests skip unless AINEWS_TEST_POSTGRES_URL is set; CI sets it with a postgres:18-alpine service. Separately, the legacy cleanup refused to run when any table had an unknown FK to articles (that cleanup and its guard were removed 2026-10-21).",
      "fix": "Run the suite against a local Postgres like CI: docker run -d --rm --name ainews-pg-test -e POSTGRES_USER=ainews_test -e POSTGRES_PASSWORD=isolated_ci_test -e POSTGRES_DB=ainews_test -p 55432:5432 postgres:18-alpine, then AINEWS_TEST_POSTGRES_URL=postgresql+psycopg://ainews_test:isolated_ci_test@127.0.0.1:55432/ainews_test in the clean-copy run.",
      "verification": "Full suite with the URL set: 1082 passed, 0 skipped."
    },
    {
      "id": "sqlite-reused-article-id-inherits-signals",
      "date": "2026-10-19",
      "area": "storage/daily_signals",
      "symptom": "On local SQLite a newly fetched article shows as already extracted for daily signals, or appears in an older day's observations with another article's entities; on PostgreSQL the same flow is correct.",
      "evidence": [
        "PR #39 review (A-claude A04, A-gpt A05/A06): delete an extracted article, insert a new one that gets the same id, publish it in a digest",
        "tests/unit/test_daily_signals_repo.py enabled PRAGMA foreign_keys=ON, unlike the app"
      ],
      "cause": "The app never enables SQLite foreign keys, so ON DELETE CASCADE does not remove article_signals and daily_signal_scope rows of a deleted article, and SQLite reuses the highest rowid. Rows keyed by article_id alone were inherited by the new article.",
      "fix": "Key scope, extraction rows, coverage, observations and evidence writes by (article_id, url_canonical_hash); both tables store url_canonical_hash and a stale row is ignored or taken over and reset. The global SQLite pragma stays unchanged. Commit a1a91bd (F9).",
      "verification": "test_reused_article_id_without_fk_enforcement_inherits_nothing (no FK pragma) fails on 8f30549 and passes after the fix; full suite with PostgreSQL green."
    },
    {
      "id": "daily-digest-dropped-provider-connection",
      "date": "2026-10-20",
      "area": "daily publication (daily-publish)",
      "symptom": "Nightly digest ends `failed_preserved_previous` with reason `provider_outage_unknown_billing`; daily-signals does not run; a plain rerun of scripts/run_daily_digest_job.sh stops at once with `unknown_or_failed_previous_call_requires_review`.",
      "evidence": [
        "data/daily-enrichment/2026-10-19/journal.sqlite3: one deepseek call state=failed, error_type=ReadError, reserved 2026-10-20 02:00:50 UTC",
        "logs/daily-digest.log report for 2026-10-19"
      ],
      "cause": "An httpx transport error (connection dropped while reading the answer) leaves a call whose billing is unknown. The daily journal had no transport_review_reason, so the call was never retried and every later dispatch was blocked.",
      "fix": "src/app/core/daily/enrichment.py passes TRANSPORT_REVIEW_REASON and TRANSPORT_RETRY_DELAYS=(60, 300) to PilotJournal: the reservation is kept and the request is retried after 1 and 5 minutes in the same run. After the third failure the day fails with `Reviewed transport attempts exhausted`. Journals from before the fix resume through the same path (the failed row is reviewed automatically).",
      "verification": "tests/unit/test_daily_enrichment.py::test_dropped_connection_is_retried_after_one_then_five_minutes and ::test_transport_retries_exhausted_fails_day_without_more_dispatch; 2026-10-19 was published on 2026-10-20 by reviewing the row and running publish_day with the same reason."
    },
    {
      "id": "mypy-app-imports-are-any",
      "date": "2026-10-20",
      "area": "make lint (mypy)",
      "symptom": "mypy reports `Returning Any from function declared to return \"str\"` [no-any-return] (or int, tuple[int, int]) on a line that returns the result of a typed project function or a Settings field, e.g. `return jev_state(article)` in src/app/core/ingestion/admission.py.",
      "evidence": ["mypy names project modules `src.app.core.ingestion.pipeline` in its messages, so `from app... import ...` does not resolve and falls under ignore_missing_imports", "pyproject.toml [tool.mypy]: files = [src, tests], explicit_package_bases, ignore_missing_imports and warn_return_any are on"],
      "cause": "Under this config every name imported from `app.*` is Any, and warn_return_any flags returning it from a function with a typed return.",
      "fix": "Follow the existing idiom: `cast(str, ...)` (see `_html_placeholder_key` in src/app/core/ingestion/pipeline.py) or assign to a typed local (`counts: tuple[int, int] = ...; return counts`). Do not add `# type: ignore`.",
      "verification": "make lint passes after the cast or typed local (branch refactor/pipeline-cleanup-20261020)."
    },
    {
      "id": "testclient-cookie-override-httpx2",
      "date": "2026-10-21",
      "area": "tests (auth, Starlette TestClient)",
      "symptom": "In CI only, tests/unit/test_auth_stage1.py::test_tampered_session_token_is_denied, ::test_second_login_immediately_invalidates_previous_session_token and tests/e2e/test_auth_e2e.py::test_e2e_second_login_immediately_invalidates_previous_session_token fail with `assert 200 == 401`; they pass locally. Master failed the same way on a rerun, so the PR under test was not the cause.",
      "evidence": ["CI installed httpx2/httpcore2 2.16.0 (2.15.1 the day before); they are not pinned and come in through mcp", "Starlette 1.9 TestClient uses httpx2 when it is installed", "with httpx2 2.16 the login cookie is stored for domain testserver.local, and client.cookies.set(name, value) adds a second cookie with an empty domain; the request carries `s=OLD; s=VALID` and the server reads the valid one"],
      "cause": "Test client cookie jar behavior, not the auth code: the test did not replace the session cookie, it added one. Browsers replace a cookie of the same name, domain and path.",
      "fix": "Call client.cookies.clear() before client.cookies.set(...) when a test presents a chosen token.",
      "verification": "The auth tests pass with httpx2 2.15.1 and 2.16.0 (local venv from build/requirements-dev.txt)."
    },
    {
      "id": "rclone-lsf-empty-prefix-dir-not-found",
      "date": "2026-10-21",
      "area": "scripts/db_offsite_upload.sh",
      "symptom": "`rclone lsf offsite:<bucket>/monthly/ --include ...` prints `error listing: directory not found` and exits non-zero on the first upload of a new bucket.",
      "evidence": ["Reproduced in ubuntu:24.04 with rclone 1.60 (apt) and a local remote before monthly/ existed"],
      "cause": "On bucket and object stores a prefix with no objects is not a directory, so rclone reports it as not found instead of an empty list.",
      "fix": "List the bucket root recursively and filter: `rclone lsf -R --files-only <remote> --include \"/monthly/postgres_<YYYYMM>*\"`.",
      "verification": "Container test: first upload writes daily/ and monthly/, a second upload of the same month writes only daily/."
    },
    {
      "id": "macos-join-options-after-files",
      "date": "2026-10-21",
      "area": "scripts/db_offsite_restore_test.sh",
      "symptom": "Restore test on macOS restores fine, then prints `usage: join [-a fileno | -v fileno ] ...` at the prod comparison.",
      "evidence": ["First real restore test from B2 on the owner's Mac, 2026-10-21"],
      "cause": "BSD join (macOS) stops option parsing at the first file name; GNU join accepts options after the files.",
      "fix": "Put all join options before the two file names.",
      "verification": "Rerun on macOS: per-table restored vs prod counts printed, all 29 tables equal."
    }
  ]
}
```
