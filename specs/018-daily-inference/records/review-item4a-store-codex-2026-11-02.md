1. **P2 — Missing article IDs:** [bulletin_store.py:43](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4a-store/src/app/storage/bulletin_store.py:43). Building a story from article `123` stores its URL and text but loses `123`, violating FR-007. **Fix:** carry article IDs through `Candidate` → grouped `Story.article_ids`; assert explicit IDs in storage/API tests.

2. **P2 — Refusal leaves stale session objects:** [bulletin_store.py:51](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4a-store/src/app/storage/bulletin_store.py:51). Reproduced: session A loads an unposted day; B posts it with ID `42`; A’s save returns `False`, but A’s subsequent `get()` still shows no Telegram ID and the old payload. Database contents remain protected. **Fix:** refresh the existing identity on refusal; add a two-session regression test.

3. **P3 — `replaced` can be logged incorrectly:** [bulletin_store.py:36](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4a-store/src/app/storage/bulletin_store.py:36). Reproduced: A reads an absent day, B inserts it, A’s upsert replaces B’s row but logs `replaced=false`. **Fix:** derive insertion/replacement from database write results rather than the preliminary read.

Mutation results, executed in memory without source edits:

| Mutation | Test that catches it |
|---|---|
| Drop protection `WHERE` | `test_posted_day_is_never_replaced`, `test_cli_posted_day_exits_zero` |
| Store during dry run | `test_cli_dry_run_stores_nothing`, written-day dry-run cases |
| Reverse latest ordering | `test_latest_ready_skips_skipped_days` |
| Leak Telegram ID | `test_api_bulletin_by_date` |
| Remove public-path registration | `test_api_bulletin_is_public` and other API tests |

**Survivors:** removing `populate_existing`; changing 503 to 500. Add held-object refresh and storage-failure API assertions.

Requested tests: **65 passed, 1 warning**. Migration has one head; PostgreSQL types match between model and migration. PostgreSQL execution was not tested. **Changes required before merge.**