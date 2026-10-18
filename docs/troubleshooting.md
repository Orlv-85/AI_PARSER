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
      "cause": "The PostgreSQL integration tests skip unless AINEWS_TEST_POSTGRES_URL is set; CI sets it with a postgres:18-alpine service. Separately, legacy cleanup refuses to run when any table has an unknown FK to articles, so a new table referencing articles must be declared to that guard.",
      "fix": "Run the suite against a local Postgres like CI: docker run -d --rm --name ainews-pg-test -e POSTGRES_USER=ainews_test -e POSTGRES_PASSWORD=isolated_ci_test -e POSTGRES_DB=ainews_test -p 55432:5432 postgres:18-alpine, then AINEWS_TEST_POSTGRES_URL=postgresql+psycopg://ainews_test:isolated_ci_test@127.0.0.1:55432/ainews_test in the clean-copy run. For a new FK to articles, extend legacy_cleanup.known_article_fk (derived signals tables are accepted only with ON DELETE CASCADE).",
      "verification": "Full suite with the URL set: 1082 passed, 0 skipped."
    }
  ]
}
```
