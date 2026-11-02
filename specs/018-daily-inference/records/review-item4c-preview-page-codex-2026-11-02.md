- **P2 — [pages.py:135](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4c-preview-page/src/app/web/routes/pages.py:135): new route increases existing complexity.** Cr​apper’s analyzer confirms `build_pages_router` CC **21 → 25** versus `origin/master`; the reported CRAP 25.2 is not wholly inherited. This is a structural finding, with no failing request. **Fix:** move the lookup, rendering and exception handling into a module-level helper, leaving a thin route wrapper. `create_app` remains CC **25 → 25**.

No functional or security defect found for builder/writer-produced rows. Stored story order, fallbacks, escaping, URL restrictions, date boundaries, packaging and route registration match the contract. Malformed dates return JSON 400, which the agreed scope permits. `create_all()` matches the existing digest route. Recommendation: expose the shared `_parse_day` as `parse_day`; nonblocking.

Mutation results **by static analysis**—execution was blocked before tests by sandbox denial of temporary files:

| Mutation | Expected result |
|---|---|
| Drop headline escaping | Killed by `test_bulletin_page_escapes_stored_text` |
| Allow any URL scheme | Killed by `test_bulletin_page_escapes_stored_text` |
| Show next link for today | Killed by `test_bulletin_page_prev_next_links` |
| Return 200 for missing row | Killed by `test_bulletin_page_missing_day_is_404` and `test_bulletin_page_empty_store_is_404` |
| Skip `rubric_story` | Killed by `test_bulletin_page_shows_ready_day` |
| Remove `/bulletin` from public paths | **Survives, behaviorally equivalent:** middleware already allows non-admin page paths |

Requested scoped tests, through the approved launcher: **53 passed, 1 warning, exit 0**. Files were not edited.