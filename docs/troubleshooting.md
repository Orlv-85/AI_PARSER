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
    }
  ]
}
```
