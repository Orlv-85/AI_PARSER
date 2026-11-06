# Prompt (Codex, gpt-6.1-sol high): spec 018 item 6b, bulletin home page behind the switch, digest at /daily, page counter (2026-11-06)

Repo `ai-news-collector`. Work only in this directory (a git worktree, branch
`feat/018-item6b-home-page`, from origin/master):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item6b-home-page`. Do not touch any
other directory. Do not run git commit, push or any gh command. No network, no paid calls. Do not
spawn a doc review or any sub-agent: a separate reviewer (another model) reviews the code and the
doc after you.

Speed rule: while working run only the feature's tests and `ruff` on changed files; at the end run
the full suite, `make lint`, crapper, dryer and mutator once each, in that order; after a fix rerun
only the check that failed.

Commands: `E="env PYTHONPATH=src PATH=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin:$PATH PIP_NO_INDEX=1 PYTHONDONTWRITEBYTECODE=1"`;
pytest is `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest` (always with `PYTHONPATH=src`,
otherwise the main folder's code is imported).

## Scope

Spec `specs/018-daily-inference/spec.md`: User Story 2, FR-009, FR-010, FR-019, FR-023. Item 6a
(merged, #214) gave `/bulletin` its design (`src/app/web/bulletin_view.py`, `bulletin.html`,
`static/css/bulletin.css`); its open points are in
`specs/018-daily-inference/records/report-item6a-bulletin-design-2026-11-05.md` "Open points for 6b".
6b wires the design to `/` behind the switch. The switch stays off in production; with it off, what
visitors of `/` see must not change at all.

## Decisions already made (put them in the doc's Decisions as "decided 2026-11-06 (agent)" unless a source is named)

1. `GET /daily` serves the digest page exactly as `/` does today (same query parameters, same HTML,
   same 503), whatever the switch. Public like `/` (add it to the unprotected paths in
   `src/app/web/app.py`).
2. `GET /` with `bulletin_home_page` off: the digest, unchanged (User Story 2 scenario 5). With it on:
   the bulletin of `?date=` or the latest ready day, in the 6a design, **without** the checking block
   and **without** `noindex`. Old links `/?date=D` show the bulletin of D with its "Full report" link
   (scenario 2). With the switch on and no ready bulletin stored at all, `/` without a date shows the
   digest (a site never shows an empty home page). A date without a row: 404 page that says so and
   links to `/daily?date=D` (scenario 4). Bad date: 400, storage failure: 503, as the preview.
3. `/bulletin` stays the hidden preview: noindex, checking block, unlinked; its links change as in 4.
4. Digest links point to `/daily`: "Full report (N) →" uses the stored `full_report_url`
   (`/daily?date=D`); the skipped-day and missing-day links go to `/daily?date=D`; `period.html`
   "Daily Digest" and `period_view.py` day links go to `/daily...`; `static/js/digest.js` builds the
   date-picker URL on the current path, so clearing the date on `/daily` stays on `/daily`. Find every
   other link to the digest (`rg -n '"/"|/\?date=' src/app/web`) and change it the same way.
5. Skipped day on `/` and `/bulletin`: a plain reader sentence instead of the stored reason code
   (owner yes 2026-11-06), e.g. "No bulletin was issued for this day." plus the digest link; the
   reason code stays only in the checking block of `/bulletin`. One mapping, unknown codes fall back
   to the generic sentence. Find the codes in `src/app/core/bulletin/daily.md` and the builder.
6. Date choice on the bulletin home (User Story 2: "a date picker for earlier days"): keep the 6a
   previous/next links and add a plain `<form method="get">` with `<input type="date" name="date">`
   (no JavaScript).
7. FR-023 page counter: table `page_views (day DATE, route TEXT, count INTEGER, PRIMARY KEY (day,
   route))`, Alembic migration, a small repo with one atomic increment (insert or add 1, safe under
   concurrent requests on PostgreSQL and SQLite: dialect `on_conflict_do_update`). Counted: a `GET`
   answered 200 by `/` (route `/`, whatever it showed) and by `/daily` (route `/daily`), day = UTC
   today. No IP, no user agent, no cookie, nothing else stored. A counting failure is logged and
   never changes the response. Read-only CLI `ai-news page-views [--days N]` (default 14) prints one
   JSON object `{day: {route: count}}`.
8. `docker-compose.prod.yml` forwards `AINEWS_BULLETIN_HOME_PAGE: ${AINEWS_BULLETIN_HOME_PAGE:-false}`
   to the app (the container gets only listed variables: `docs/troubleshooting.md` case
   `prod-env-var-not-forwarded-by-compose`), with a test like
   `test_production_compose_forwards_world_stream_switch_default_off`.
9. `bulletin_post_channels` is not touched (phase B).

## Steps (doc first, then failing tests, then code)

1. Read `AGENTS.md`, `src/app/web/pages.md`, `src/app/web/routes/pages.py`, `src/app/web/app.py`,
   `src/app/web/bulletin_view.py`, `src/app/web/period_view.py`, `src/app/web/static/js/digest.js`,
   `src/app/storage/bulletin_store.md`, `src/app/core/bulletin/daily.md`, `src/app/config/settings.py`,
   an existing Alembic migration under `src/app/storage/migrations/versions/` (latest head:
   `ls -t`), `tests/unit/test_semantic_admission_compose.py`, and the page tests
   (`rg -l "bulletin_page|build_pages_router|def test_index" tests`).
2. Doc: `src/app/web/pages.md` gets the home page, `/daily` and the counter (Behavior rules with test
   names, Decisions above, Invariants: switch off means `/` byte-identical to `/daily`; no counter
   data about visitors; `/bulletin` stays unlinked; Code map rows incl. the table and migration).
   If the counter gets its own module, cover it in `pages.md`'s `covers:`. Update
   `docs/configuration.md` (`AINEWS_BULLETIN_HOME_PAGE` is no longer "reserved") and `docs/cli.md`
   (`ai-news page-views`).
3. Failing tests first (run them, see each fail for the expected reason), at least:
   `test_daily_serves_the_digest`, `test_daily_is_public`, `test_home_is_digest_when_switch_off`
   (equal to `/daily` output), `test_home_shows_latest_bulletin_when_switch_on`,
   `test_home_old_date_link_shows_that_bulletin`, `test_home_without_ready_bulletin_shows_digest`,
   `test_home_missing_day_is_404_with_daily_link`, `test_home_has_no_checking_block_and_is_indexable`,
   `test_home_date_form`, `test_full_report_links_daily`, `test_skipped_day_plain_sentence`,
   `test_period_links_point_to_daily`, `test_page_views_counts_home_and_daily`,
   `test_page_views_failure_keeps_page`, `test_page_views_stores_no_visitor_data`,
   `test_cli_page_views_prints_json`, `test_production_compose_forwards_home_page_switch_default_off`,
   and a PostgreSQL integration test for the atomic increment next to
   `tests/integration/test_bulletin_store_postgres.py` (skipped without `AINEWS_TEST_POSTGRES_URL`).
   Keep every existing test green; update an existing test only where a link moved to `/daily`, and
   list each such update in the report.
4. Code: the smallest change in the files above; functions under CRAP 10.
5. Checks once at the end, in this order, from the worktree root:
   - `$E /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts=` (full suite)
   - `$E make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/python`
   - `$E python scripts/check_code_docs.py`
   - `$E ~/tools/unclebob/crapper/crapper <changed src .py files>`
   - `~/tools/unclebob/dryer/dryer --threshold 0.8 <changed src .py files>`
   - `$E ~/tools/unclebob/mutator/mutator --use-existing-coverage --test-command "/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts= <the feature test files>" <each changed src .py file, one run each>`
     (kill survivors in new code with tests, or give a reason per survivor).

## Report

Write `specs/018-daily-inference/records/report-item6b-home-page-2026-11-06.md` in the worktree:
files changed; each decision as implemented; each new test and how it failed before the code;
existing tests changed and why; full-suite and lint results with counts; crapper (max CRAP of
changed functions), dryer and mutator output (killed/survived, reasons); anything not run and why;
the operator steps to turn the home page on (prod `.env` line, which tag), for the coordinator.
