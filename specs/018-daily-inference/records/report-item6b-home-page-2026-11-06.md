# Item 6b: switched bulletin home, digest and page views

Worktree: `docs/work/worktrees/item6b-home-page`, branch `feat/018-item6b-home-page`.
No commit, push, gh command, network request, paid call or sub-agent was used.
The independent code/doc review remains for the separate reviewer named in the prompt.

## Implementation and decisions

1. `/daily` is public and uses the former home digest renderer, query date validation and
   storage 503. It is available with either switch value. The off-switch home and `/daily`
   return identical HTML bytes for the same selected date.
2. The existing `bulletin_home_page` setting selects a requested bulletin or latest ready row
   at `/`. Home omits checking and robots noindex; dated missing rows give 404 plus the daily
   link, malformed dates give 400, and storage failure gives 503. With no explicit date and no
   ready row, home falls back to the digest, including when only skipped rows exist.
3. `/bulletin` stays public, unlinked, noindex/nofollow and diagnostic, independent of the switch.
4. Full report uses stored `full_report_url` and item count. Skipped/missing links, period
   header/day links and the stats backlink now target `/daily`. The digest script retains
   `window.location.pathname` both when selecting and when clearing its date.
5. One mapping covers `no_digest`, `no_signals`, `signals_partial`, `signals_unavailable`, and
   `no_assessments`; unknown reasons use the generic sentence. The raw reason appears only in
   the preview checking block. The plain sentence follows the owner's 2026-11-06 decision.
6. Home keeps adjacent-date links, now on `/`, and adds a native GET date form with a submit
   button. Preview navigation stays on `/bulletin`.
7. `page_views` contains exactly day DATE, route TEXT and count INTEGER, with a composite
   day/route primary key. A dialect upsert increments in one statement; the caller commits.
   Counts cover only 200 GETs of `/` and `/daily`, using UTC today rather than the report date.
   Separate counting transactions and logged exceptions preserve page responses on failure.
   `ai-news page-views [--days N]` reads JSON totals for N calendar days including today,
   defaulting to `PAGE_VIEWS_DEFAULT_DAYS` (14), without creating tables or writing rows.
8. Production compose forwards `AINEWS_BULLETIN_HOME_PAGE` with false as its default, following
   troubleshooting case `prod-env-var-not-forwarded-by-compose`.
9. Channel posting and `bulletin_post_channels` are unchanged.

Technical choice settled from source: the actual migration head is `d2a6f8b03c19`, although
`ls -t` puts the period migration first. The new migration follows the actual head, keeping
one chain. Technical choice decided by agent: use Pydantic's date adapter in the off-switch
home so its validation matches `/daily`, while the on-switch home uses preview's strict parser.
These decisions are also recorded in `src/app/web/pages.md`.

## Files

- `src/app/web/pages.md`: intended behavior, tests, decisions, invariants and code map;
  covers the new counter module/migration and period view.
- `src/app/web/routes/pages.py`: shared digest read/render, `/daily`, switched home, counter
  calls and validation; preview still uses the same stored lookup/error helper.
- `src/app/web/bulletin_view.py`, `bulletin.html`: shared reader/preview shell, checking
  isolation, plain skips, stored Full report link, navigation and home form.
- `src/app/web/app.py`: explicit public `/daily` entry.
- `src/app/web/period_view.py`, `period.html`, `news_stats.html`: moved digest links.
- `src/app/web/static/js/digest.js`: keep the current date-picker path.
- `src/app/storage/page_views.py`, `models_sql.py`: counter repository and model.
- `src/app/storage/migrations/versions/a6b0180c0001_add_page_views.py`: idempotent upgrade and
  downgrade, following `d2a6f8b03c19`.
- `src/app/cli/main.py`: read-only page-views command.
- `docker-compose.prod.yml`, `docs/configuration.md`, `docs/cli.md`: switch forwarding and
  operator documentation.
- New tests: `tests/unit/test_web_home_page.py`, `tests/unit/test_page_views.py`,
  `tests/integration/test_page_views_postgres.py`.
- Updated tests: `test_semantic_admission_compose.py`, `test_web_bulletin_page.py`,
  `test_web_period_page.py`, `test_web_route_table.py`, `test_period_signals_migration.py`
  under `tests/unit/`.

## Test first evidence

Behavior doc was edited first, then tests, then implementation. The first new-test run had
35 failures, 9 passes and 1 skip. The initially too-weak home indexability test was strengthened
to require the bulletin masthead and rerun before implementation: it failed on the digest.

| New test | Failure before implementation |
| --- | --- |
| `test_daily_serves_the_digest` (four cases) | `/daily` was 404 |
| `test_daily_is_public` | `/daily` was 404 |
| `test_home_is_digest_when_switch_off` | Home HTML differed from `/daily`'s 404 |
| `test_home_shows_latest_bulletin_when_switch_on` | No bulletin time element on home |
| `test_home_old_date_link_shows_that_bulletin` | Digest heading instead of requested bulletin |
| `test_home_without_ready_bulletin_shows_digest` (two cases) | `/daily` was 404 |
| `test_home_missing_day_is_404_with_daily_link` | Home was 200 |
| `test_home_has_no_checking_block_and_is_indexable` | Strengthened test: missing bulletin masthead |
| `test_home_date_form` | No GET form |
| `test_full_report_links_daily` (home/preview) | Missing home link; preview used `/?date=` |
| `test_skipped_day_plain_sentence` (six reasons) | No reader skip sentence on home |
| `test_period_links_point_to_daily` | Period header still linked to `/` |
| `test_digest_date_picker_keeps_current_path` | Script reset clearing to `/` |
| `test_home_errors` (four dates) | Off-contract 422 instead of 400 |
| `test_digest_errors_match` | `/daily` returned 404 instead of matching digest errors |
| `test_page_views_counts_home_and_daily` | `/daily` was 404; counter table absent |
| `test_page_views_failure_keeps_page` | Counter table did not exist |
| `test_page_views_stores_no_visitor_data` | `/daily` was 404; table absent |
| `test_cli_page_views_prints_json` | Counter table absent |
| `test_page_views_empty_cli` | Missing CLI command (exit 2) |
| `test_page_views_sqlite_atomic_increment` | Repository module absent |
| `test_page_views_migration` | Migration module absent |
| `test_production_compose_forwards_home_page_switch_default_off` | Missing environment key |
| `test_news_stats_links_daily` | Stats backlink still pointed to `/`; run before fixing it |

`test_page_views_counts_digest_home_and_fallback` and `test_page_views_uses_utc_today` are
additional verification tests added after the implementation; they passed on their first run.
The PostgreSQL concurrent-increment integration test was written before implementation but is
skipped without `AINEWS_TEST_POSTGRES_URL`; no live PostgreSQL claim is made.

Existing test updates, each listed explicitly:

- `test_bulletin_page_skipped_day_links_digest`: `/daily` target and the required plain sentence.
- `test_bulletin_page_missing_day_is_404`: `/daily` target only.
- `test_bulletin_page_full_report_links_digest`: stored `/daily` URL instead of a synthesized
  home link; removed its old assertion forbidding `/daily`.
- `test_ready_week_shows_sections_in_order`: `/daily` day-link prefix only.
- `test_bulletin_page_status_pages_share_shell`: skipped preview now has checking details to
  hold the raw reason; other status pages still have no details.
- Pinned `_ROUTE_TABLE` and `_OPEN_ROUTES`: added the new public `/daily` route, preserving
  every existing route's row and relative order.
- `test_single_head_and_chain`: the final full suite found its hardcoded old head; advanced
  the head expectation and retained the previous parent assertion plus the new parent assertion.

The prompt's instruction to update existing tests only for moved links conflicts with its
required skipped checking block, new route and migration, which existing assertions explicitly
forbid. Those minimal assertion updates implement the requested behavior and preserve the
rest of those tests; no unrelated assertions were weakened.

## Validation

All commands ran from the worktree with `PYTHONPATH=src`, the main checkout's installed venv
on PATH, `PIP_NO_INDEX=1` and `PYTHONDONTWRITEBYTECODE=1` where specified. Databases were
temporary/isolated. Logs and quality artifacts are under ignored `target/` and `.metrics/`.

- Full suite, requested command, once: **1 failed, 2,413 passed, 3 skipped**, 6 warnings,
  145.05 seconds. Only failure: old head constant in `test_single_head_and_chain`.
  After updating that expectation, reran only that failed test: **1 passed**. The full suite
  was not repeated, following the speed rule; this is not a claim of a fresh all-green full run.
- `make lint`: **passed**; Ruff passed, mypy reported no issues in **279 files**, pylint
  **10.00/10**. It ran before the later mutation-test additions; scoped Ruff on those test
  additions and the head-pin update passed afterwards.
- `python scripts/check_code_docs.py`: **15 checked, ok**; final documentation-only recheck
  also covers the additional test references.
- Crapper, once across all eight changed source Python files: coverage command ran only the
  feature test files (**163 passed**) and wrote `target/coverage/python/lcov.info`, avoiding
  another full-suite run. New/changed feature leaf functions have **100% coverage** and max
  **CRAP 8.0**, shared by `render_bulletin_page` and `_bulletin_response`. Counter repo and
  migration functions score 2.0, counter CLI 1.0, skip status 7.0, checking/ready/shell 3.0.
  The tool aggregates nested route functions into `build_pages_router`: **32.9 (CC 21,
  coverage 70%)**; `create_app` is **25.2 (CC 25, 93.8%)**. These existing enclosing functions
  remain above 10, so the literal all-changed-functions-under-10 target is not fully met.
  The largest score in the named files is unrelated `period_signals` CLI, **272.0**, because
  feature-only coverage does not exercise it. No unrelated CLI/auth refactor was made to
  reduce inherited scores.
- Dryer, once, threshold 0.8 across those files: **No duplicate candidates found**.

Mutation checks ran once per changed Python file, with existing LCOV coverage. Existing modules
were limited to added/replaced lines (`--lines`); both new modules were checked in full. This
does not claim whole-file mutation coverage of unrelated existing code. The tool lists other
unselected/uncovered file sites in its totals; those are not added-code test gaps.

The first runs exposed a reason-mapping survivor, the PostgreSQL dialect-selection survivor,
and three migration schema survivors. Added `test_skipped_day_explains_missing_digest`,
`test_page_views_increment_compiles_for_postgres`, and PK/nullability assertions to the
migration test. Added `test_bulletin_renderer_defaults_to_preview` and
`test_bulletin_preview_is_hidden_from_openapi` for implicit-preview defaults and schema hiding.
The two affected test files then passed **42 tests**. These are mutation-driven test
strengthenings, not new production-code changes.

LCOV omitted executed multiline SQL/default-argument sites, matching troubleshooting case
`mutator-lcov-multiline-sites-uncovered`. Only their specific lines and actual survivors were
rerun with `--no-coverage --lines ...`, as documented in that case. Cumulative unique selected
site results after the reruns:

| Source | Killed | Survived | Selected sites still uncovered |
| --- | ---: | ---: | ---: |
| `src/app/cli/main.py` | 4 | 1 | 0 |
| `src/app/storage/models_sql.py` | 0 | 0 | 0 |
| `src/app/web/app.py` | 0 | 0 | 0 |
| `src/app/web/bulletin_view.py` | 8 | 0 | 0 |
| `src/app/web/period_view.py` | 0 | 0 | 0 |
| `src/app/web/routes/pages.py` | 12 | 0 | 0 |
| `src/app/storage/page_views.py` | 6 | 0 | 0 |
| `src/app/storage/migrations/versions/a6b0180c0001_add_page_views.py` | 3 | 0 | 0 |
| **Total** | **33** | **1** | **0** |

The sole survivor is `src/app/cli/main.py:96`, `sort_keys=True` to `False`. It is equivalent for
the specified JSON-object contract: object key order has no semantic effect, and JSON parsing
returns the same day/route/count mapping. No test of incidental byte ordering was added.
The model/app/period changes have no supported mutation operators on the selected added lines
(the app/period edits add or move string links; the model adds declarative columns).

Initial logs: `target/item6b-checks/mutator-0.log` through `mutator-7.log`, in the table's order.
Targeted reruns: `mutator-recheck-bulletin.log` (lines 122,131),
`mutator-recheck-pages.log` (112,196), `mutator-recheck-counter.log` (21,24,28), and
`mutator-recheck-migration.log` (23,24,25), in the same directory. Existing-coverage runs used
the feature files listed in `crapper.log` without its coverage flags; targeted reruns used the
same files, with the four later regression tests included. Every rerun baseline was green.

Not run: live PostgreSQL integration (URL unset; no network allowed), visual browser QA of
the inherited design/form, independent reviewer session (explicitly deferred), another full
suite or full lint after test-only mutation strengthening (speed rule), unrelated whole-file
mutation sites, and commit/push/release/deploy (explicitly outside this task).

## Operator handoff

This work is **unreleased**. Local base tag is `v0.1.160`; it does not contain these changes.
No release tag was assigned or created in this task. The coordinator must select and record
the next release tag containing the reviewed/merged item 6b; do not turn this on using v0.1.160.

1. Release/deploy that new tag normally, applying Alembic migration `a6b0180c0001` before
   enabling the feature. Keep the switch false during deployment/review.
2. Check stored ready issues through the still-unlinked `/bulletin?date=D` preview and verify
   `/daily?date=D`. Confirm at least one ready bulletin exists if home should show a bulletin.
3. After the owner's rollout decision, put `AINEWS_BULLETIN_HOME_PAGE=true` in `/opt/ai-news/.env`.
   Export `APP_IMAGE` from `.last_deploy_image` in that directory and recreate the app with
   `docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate app`.
   Recreating is necessary for the changed environment to reach the container.
4. Check `/`, an old `/?date=D` link, `/daily`, and a missing date. Read totals using
   `docker compose -f docker-compose.prod.yml run --rm app ai-news page-views --days 14` with
   that same `APP_IMAGE` exported.
5. To restore digest home, set the line false and recreate the app again. No data rollback or
   channel switch is needed. This task did not change production or enable the switch.

No prompts for another session were generated. Preserve the repository handoff rule: save any
future prompt before handing it over, under this feature's `records/`, without overwriting an
earlier prompt; keep reviews and reports there too.

## Review fixes

The PR #217 follow-up prompt was applied in the same worktree, after the coordinator committed
the initial implementation and corrected the doc coverage. No commit, push, gh command,
network request, paid call or sub-agent was used in this follow-up. `period_view.py` was not
added back to `pages.md` coverage.

### Changes and test-first evidence

Behavior and Decisions in `src/app/web/pages.md` were updated first. Before implementation,
the new regression tests produced **11 failures and 2 passes**:

- `test_page_views_runs_after_response` (eight combinations): the counter appeared before
  response start/body in the recorded ASGI event order. Covers digest home, empty-store fallback,
  ready bulletin home, `/daily`, and both successful and failing counters. After the fix, the
  response's final body is sent before the counter runs, and counter failures still only log.
- `test_page_views_transaction_timeouts[postgresql]`: no timeout statements preceded the upsert.
  `PageViewRepo.increment` now issues `SET LOCAL lock_timeout = '1s'` and
  `SET LOCAL statement_timeout = '2s'` in the same session transaction before its PostgreSQL
  upsert. The SQLite case was already green and verifies those statements are skipped.
- `test_home_date_openapi_matches_daily`: `/` lacked `format: date`. The home parameter now
  uses Pydantic `WithJsonSchema` to restore exactly the same optional date parameter schema as
  `/daily`, without changing its string input or switched-on 400 validation. The pinned
  expected schema matches origin/master's date parameter (name `date`, optional, title `Date`,
  string date or null, with no explicit schema default). Existing malformed-date tests stay green.
- `test_page_router_handlers_only_delegate`: failed on the branching `index` body. It checks
  the explicitly requested handler structure with AST; behavior-only tests cannot distinguish
  this refactor. Branching home, stats, login page, collection status, login and logout bodies
  now live in module-level helpers; every nested route handler delegates. Existing route-table,
  authentication and HTML tests preserve route names, order, response models and responses.

The already-green `test_page_views_create_all_before_background` verifies the coordinator's
unchanged decision: page reads retain `deps.create_all()`, and a missing `page_views` table is
created before the deferred count. It or the idempotent migration can create the table first.

Files changed: `src/app/web/routes/pages.py`, `src/app/storage/page_views.py`,
`src/app/web/pages.md`, `tests/unit/test_web_home_page.py`, `tests/unit/test_page_views.py`,
and this appended report section. No existing test assertion was relaxed or removed.

Scoped feature validation after implementation: **191 passed**, six existing deprecation
warnings; scoped Ruff passed. Final ordered check results and CRAP/mutation scores follow below.

### Ordered final checks

Logs for this follow-up are in ignored `target/item6b-review-checks/`. Every pytest invocation
used `PYTHONPATH=src` and the installed main-checkout venv, with no network or package installs.

1. Full suite, once: **2,431 passed, 3 skipped**, six deprecation warnings, **143.41 seconds**
   (`full-suite.log`). The PostgreSQL integration tests remain skipped without
   `AINEWS_TEST_POSTGRES_URL`; no live PostgreSQL claim is made.
2. `make lint`: Ruff passed and mypy found no issues in **279 files**. Pylint identified two
   test-only issues: eight positional fixture parameters and an unused setup-only `client`
   fixture argument. Made the four parameterized case arguments keyword-only and declared
   the setup fixture with `pytest.mark.usefixtures`. Reran only the failed pylint target:
   **passed, 10.00/10** (`lint.log`, `lint-pylint-recheck.log`). No production code changed after
   the full suite; the later coverage/mutation baselines also run those adjusted tests.
3. `python scripts/check_code_docs.py --diff origin/master --strict`: **15 checked, ok**
   (`code-docs.log`). The coordinator's `period_view.py` coverage correction is preserved.
4. Crapper on `pages.py` and `page_views.py`, once, with threshold **9.99**: **passed**.
   Used an explicit coverage command for the eight feature/auth/static test files, **191 passed**,
   writing `target/coverage/python/lcov.info`, to avoid rerunning the whole suite. Maximum CRAP
   in both source modules is **8.0**. Scores of the factory and every newly extracted helper:

   | Function | CC | Coverage | CRAP |
   | --- | ---: | ---: | ---: |
   | `build_pages_router` | 1 | 100% | **1.0** |
   | `_digest_page` | 1 | 100% | 1.0 |
   | `_home_response` | 4 | 100% | 4.0 |
   | `_news_stats_response` | 4 | 50% | 6.0 |
   | `_login_page_response` | 5 | 100% | 5.0 |
   | `_health_response` | 1 | 100% | 1.0 |
   | `_collection_status_response` | 2 | 75% | 2.1 |
   | `_login_response` | 7 | 100% | 7.0 |
   | `_logout_response` | 4 | 100% | 4.0 |

   The updated counter `increment` scores **3.0**, at 100% coverage; existing counter `totals`
   scores 2.0. Existing `_bulletin_response` and `_render_digest` set the module maximum of 8.0.
   The factory's previous aggregate **32.9** is resolved (`crapper.log`, `.metrics/crap.edn`).
5. Dryer on those two modules at threshold 0.8, once: **No duplicate candidates found**
   (`dryer.log`).
6. Mutation checks on each complete source file use the fresh LCOV coverage, the same eight
   feature test files, `--mutate-all` (no inherited killed-site shortcuts), and four workers.
   Results and targeted follow-ups are recorded below.

### Mutation results and follow-ups

The first complete-file runs reported:

| Source | Killed | Survived | LCOV-uncovered sites |
| --- | ---: | ---: | ---: |
| `src/app/web/routes/pages.py` | 28 | 9 | 6 |
| `src/app/storage/page_views.py` | 3 | 0 | 4 |

Added four regression tests for preserved behavior, updating Behavior references before the
tests. All four passed on the production code, then killed the corresponding mutants:

- `test_extracted_login_preserves_credentials_and_json`: rejects an incorrect username even
  with the correct password; checks successful login/logout JSON and the HttpOnly cookie.
  Kills the username `and` to `or` survivor at line 228 and success JSON boolean survivor at 237.
- `test_extracted_stats_preserves_dates`: freezes UTC today, checks yesterday as the default
  end, the default range, equal bounds and reversed bounds. Kills the two default-date survivors
  at 191 and `>` to `>=` survivor at 193.
- `test_digest_renderer_preserves_escaping_and_defaults`: checks quoted URL escaping and
  unchanged text escaping, default headline/monthly navigation, and combined weekly/monthly
  links. Kills the quote-escaping survivor at 69 and exercises multiline/default sites.
- `test_legacy_weekly_redirects_stay_hidden_from_openapi`: kills the two `include_in_schema`
  survivors at 284 and 285, preserving the existing hidden legacy route metadata.

Scoped run: **4 passed**, one existing deprecation warning; scoped Ruff passed. No production
code was changed for these test gaps. The initial regressions for this review still failed
before implementation as listed above; these four are additional mutation-driven tests.

Following troubleshooting case `mutator-lcov-multiline-sites-uncovered`, reran only uncovered
and non-equivalent survivor lines with `--no-coverage --mutate-all --lines ...`:

- Pages: `52,56,69,91,113,191,193,228,237,241,277,284,285`.
- Counter: `29,33` (both mutations at each SQL line).

The same feature files, including the four new tests, were used; every baseline passed.
Cumulative unique results, including retained killed results from the first runs:

| Source | Killed | Survived | Uncovered |
| --- | ---: | ---: | ---: |
| `src/app/web/routes/pages.py` | **42** | **1** | **0** |
| `src/app/storage/page_views.py` | **7** | **0** | **0** |
| **Total** | **49** | **1** | **0** |

Sole survivor: `pages.py:251`, `_logout_response`, `and` to `or`. Equivalent for every app built
by `create_app`: `deps.auth_enabled` is true exactly when `deps.signer` is present; both versions
enter the revoke branch for enabled auth and skip it for disabled auth. The existing enabled,
disabled and no-cookie logout tests remain green. No test using an impossible dependency
combination was added merely to kill this mutant. The page mutation command therefore exits
3 for that documented equivalent survivor; the counter command exits 0.

Logs: `mutator-pages.log`, `mutator-counter.log`, `mutator-recheck-pages.log`,
`mutator-recheck-counter.log`, and `mutation-test-additions.log` under
`target/item6b-review-checks/`. Metrics are in `.metrics/mutate/`. Final strict code-doc
recheck after the extra test references: **15 checked, ok** (`code-docs-final.log`).

Not rerun: full suite, complete lint, CRAP and dryer after mutation-only test strengthening,
following the speed rule. Production code is identical to the version checked by all those
gates; CRAP scores above are the recorded pre-strengthening measurements. Not run: live
PostgreSQL, release/deploy, network/paid calls or a separate reviewer/sub-agent. The feature
remains off by default, and the coordinator retains responsibility for release and review.
