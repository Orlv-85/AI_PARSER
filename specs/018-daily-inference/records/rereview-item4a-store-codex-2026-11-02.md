- **P3 — Documentation overstates output compatibility:** [bulletin_store.md:41](/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/item4a-store/src/app/storage/bulletin_store.md:41) says stdout stays unchanged; `writer.md:128` similarly promises “byte for byte.” **Input:** `bulletin build --date D --dry-run --json` with a selected story now emits `article_ids`. **Fix:** document this additive JSON change; restrict unchanged-output claims to rendered text, writer packet, and writer summary.

All original findings and both surviving mutations now have meaningful regression coverage. No remaining code defects found.

PostgreSQL test should run in CI: the URL is configured, its unique schema isolates tables, and `finally` drops that schema. PostgreSQL execution was not performed under the no-network restriction.

Requested tests: **112 passed, 1 warning**, exit **0**. Documentation reference checker: **13 checked, ok**, exit **0**; named tests exist. No files edited.