<!-- code-doc
module: src/app/web/routes/pages.py
covers:
  - src/app/web/routes/pages.py
  - src/app/web/*.html
  - src/app/web/static/**
-->
# Web pages and static assets

The HTML pages of the site: the public digest `/`, the public weekly signals `/weekly`, the public
news stats `/news-stats`, the login page `/login` and the admin page `/admin`. Each page is a template in `src/app/web/` filled by
`build_pages_router`; its styles and scripts are files under `src/app/web/static/`, served at
`/static/`. The legacy weekly pages (`/weekly-ai-analytics`, `/weekly-ai-analytics/reports`) are
retired: they only redirect to `/weekly`.

## Behavior

```mermaid
flowchart LR
  browser["Browser"] --> route["GET page route (pages.py)"]
  route --> fill["Template + placeholders filled by the server"]
  fill --> html["HTML with link/script tags"]
  html --> assets["GET /static/... (no-cache, ETag)"]
  assets --> auth{"/static/admin/ ?"}
  auth -- "yes, no session" --> login["303 to /login"]
  auth -- "public or session" --> file["CSS / JS file"]
```

**Pages and access**
- `/`, `/weekly`, `/news-stats` and `/login` are public; `/admin` needs a session when auth is enabled and
  redirects to `/login` otherwise; `/login` with a valid session redirects to `/admin`.
  Tests: `test_unauthenticated_root_stays_public`, `test_public_digest_page_stays_public_when_auth_is_enabled`,
  `test_admin_route_is_protected_and_public_root_stays_open`, `test_login_page_redirects_when_session_valid`,
  `test_login_page_renders_login_form_when_not_authenticated`, `test_route_table_order_names_and_models_are_pinned`
  (`/weekly` is in the open routes).
- `/` shows the digest of the requested day (default: yesterday, UTC) and the Daily Signals block
  (`render_signals`); a signals read failure keeps the page. Tests:
  `test_public_digest_page_renders_digest_shell_with_yesterday_selected`,
  `test_public_digest_page_keeps_explicit_query_date_selected`, `test_signals_read_error_keeps_page`.
- `/weekly` shows one stored week (the page states are in `src/app/core/periodic/signals_period.md`,
  "Page"); it is rendered by `period_view.py` from the same stored row the API reads, in the template
  `period.html` with `digest.css` and `period.css` and no script. `?week=` takes a Monday; another
  day redirects (303) to its Monday; a missing week, text that is not a date, no rows or an unreadable
  row give the page with a plain reason line and status 200, never 500. A picker of plain links
  (previous, next, list of stored weeks) sits under the week. Tests: `test_ready_week_shows_sections_in_order`,
  `test_week_param`, `test_no_rows_is_unavailable_200`, `test_corrupt_row_is_200`,
  `test_page_references_exactly_its_static_assets`.
- The header link "Weekly" and the line "Week of Oct 19-25: weekly signals" under the daily signals
  block of `/` appear only when at least one stored week exists; both point at `/weekly`. A failed
  read hides them and keeps the page. They are filled by the server (`__WEEKLY_NAV__`,
  `__WEEKLY_LINE__`), so the client signals renderer never touches them. They are the only
  weekly elements on `/`: the legacy "Weekly AI Analytics" preview and the "Weekly Reports" link
  are gone, and `digest.js` no longer reads `/api/news/weekly-analytics`. Tests:
  `test_public_digest_page_has_no_legacy_weekly_preview`, `test_nav_link_and_home_line_follow_stored_weeks`,
  `test_home_page_survives_a_period_read_failure`.
- `GET /weekly-ai-analytics` and `GET /weekly-ai-analytics/reports` answer 308 to `/weekly` (query
  string dropped), for a logged-out reader too: they are not protected paths, so the auth middleware
  passes them. The legacy read API (`/api/news/weekly-analytics*`) and the tables stay for
  compatibility. Tests: `test_legacy_weekly_pages_redirect_308_to_weekly`,
  `test_legacy_weekly_redirect_works_with_a_session_cookie`, `test_route_table_order_names_and_models_are_pinned`,
  `test_auth_middleware_coverage_is_pinned`, `test_weekly_ai_analytics_api_returns_report_sections_for_last_7_days`
  (legacy API still answers with stored data).
- `/news-stats` has one header link, "Weekly" (`/weekly`), in place of the two legacy weekly links. No test.
- `/news-stats` defaults to the 60 days ending yesterday; `date_from` after `date_to` is a 422 (no
  test for the 422). Tests: `test_news_stats_page_renders_public_shell`.

**Placeholders**
- The server fills `__NAME__` placeholders of a template, never of a static file. Digest:
  `_render_digest` replaces all of them in one pass with `_PLACEHOLDER`, so placeholder names
  inside digest or signals text stay literal. News stats: `_render_news_stats`. Admin and login
  have none. Tests: `test_placeholders_in_digest_text_are_not_substituted`,
  `test_public_digest_page_keeps_explicit_query_date_selected`.
- The two digest script values that need the server (`initialDigestUrl`, `defaultReportDate`)
  stay in a small inline script right before the digest script, which reads them as globals.
  Tests: `test_digest_placeholders_stay_inline_before_its_script`.

**Static assets**
- Every page references exactly its asset files, in a fixed order, as classic scripts (no
  `defer`, `async` or modules) at the place of the former inline block; no page has an inline
  style block. Tests: `test_page_references_exactly_its_static_assets`.
- `/static/` is served by `_NoCacheStaticFiles`: correct content type, an ETag and
  `Cache-Control: no-cache`, so the browser revalidates and a deploy never mixes new HTML with
  old JS. Tests: `test_static_asset_is_served_with_type_and_no_cache`.
- `/static/admin/` has the protection of `/admin` (`is_protected_ui` in `auth_middleware`); the
  check runs on the normalized, lower-cased path (`..`, `//`, `.` and case do not bypass it);
  every other `/static/` path is public. Tests: `test_admin_assets_need_a_session_like_admin`,
  `test_admin_assets_check_uses_normalized_path`.
- The admin event wiring lives in `static/admin/sources.js` (the last admin script) because it uses
  functions of all admin files. No test.
- The asset files are package data of `app.web` and ship in the wheel. Tests:
  `test_web_package_data_includes_public_templates` (the globs and `period.html`; the wheel itself
  is not built in tests).

## Decisions

- Static files instead of inline blocks: a script can be read, linted and diffed on its own; the
  page template holds markup only.
- Admin assets behind the admin session: the admin code lists every admin API; it stays private
  like the page.
- `no-cache` with ETag instead of hashed file names: no build step; one revalidation per asset.
- Legacy weekly pages answer 308, not 410 or a copy (owner answer 2026-10-28; decided 2026-10-28
  (agent): 308 keeps old bookmarks working and the method; the query string is dropped because
  `?date=` of the old report means nothing on `/weekly`).
- `/news-stats` links "Weekly" instead of the two retired links (decided 2026-10-28 (agent)): a link to a
  redirect would work, but two links to one page is noise.
- No framework or bundler: the pages are small and server-rendered; classic scripts in one global
  scope keep the old execution order.
- Admin JS is four classic scripts; an exception in one file no longer stops the files after it
  (before, one inline block stopped as a whole). Accepted: affects only error cases (coordinator
  decision 2026-10-24).

## Invariants

- What a visitor or an admin sees and does does not depend on whether the code is inline or in a
  file: the asset files hold the former blocks byte for byte, in the original order.
- Concatenating the admin scripts in tag order gives the former admin script block.
- Server and client renderers of the signals block stay in step (`signals_view.py` and
  `renderSignals` in `src/app/web/static/js/digest.js`). Tests: `test_client_renderer_matches_server_classes`.
  The weekly page reuses the daily classes and the trend and link markup (`signals_view.py`), but
  has no client renderer.

## Code map

| File | Holds |
| --- | --- |
| `routes/pages.py` | Page routes, template rendering and placeholders, login/logout, health, collection status |
| `app.py` | `_NoCacheStaticFiles` mount at `/static`, `auth_middleware` (admin assets protected) |
| `routes/period.py` | `/weekly` route, `latest_week` (nav link and line on `/`), next to the period API |
| `period_view.py` | Server HTML of one stored week and the picker (`render_content`, `render_picker`, `render_page`) |
| `digest.html`, `news_stats.html`, `login.html`, `index.html`, `period.html` | Page markup; the digest also has the inline placeholder script |
| `static/css/` | `digest.css`, `news_stats.css`, `login.css`, `period.css` |
| `static/js/` | `digest.js` (digest and signals client), `news_stats.js`, `login.js` |
| `static/admin/admin.css` | Admin styles |
| `static/admin/core.js` | Shared state (`const`/`let` of the page), `setStatus`, `showPage`, page buttons |
| `static/admin/updates.js` | Settings form, run update, run status and polling (`activeScreeningMessage`) |
| `static/admin/news.js` | News view: `loadNews`, `copyVisibleLinks` |
| `static/admin/sources.js` | Source onboarding (batches, check, candidates), then event wiring and the start calls |

Where to change what: markup in the template; behavior in the asset; a new asset needs its tag in
the page, a glob in `[tool.setuptools.package-data]` of `pyproject.toml` if it is a new folder or
type, and an entry in the asset list of `tests/unit/test_web_static_assets.py`. Admin start calls and event wiring
stay in the last admin script, because they use functions of every admin file.

## Tests

- `tests/unit/test_web_static_assets.py`: asset tags per page, serving and no-cache, admin asset
  protection, digest placeholders.
- `tests/unit/test_web_period_page.py`: the `/weekly` page states, escaping, `?week=`, nav link, line on `/`.
- `tests/unit/test_web_app.py`, `tests/unit/test_web_public_digest.py`, `tests/unit/test_auth_stage1.py`:
  pages, access, signals client hooks. Tests that check moved code read the page with its assets
  (a fixture in `tests/unit/conftest.py`) or the asset file.
