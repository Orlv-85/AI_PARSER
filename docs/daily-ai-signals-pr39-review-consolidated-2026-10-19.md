# PR #39 review - consolidated findings (coordinator, 2026-10-19)

Reviewed SHA: `8f30549`. Sources (four independent reviews, none read the others):

- A-gpt: `docs/daily-ai-signals-pr39-review-a-gpt-2026-10-18.md` (10 findings, reproduced by scripts)
- A-claude: `docs/daily-ai-signals-pr39-review-a-claude-2026-10-18.md` (9 findings)
- B-gpt: `docs/daily-ai-signals-pr39-review-b-gpt-2026-10-18.md` (5 findings)
- B-claude: `docs/daily-ai-signals-pr39-review-b-claude-2026-10-18.md` (8 findings)

All four verdicts: **merge after fixes**. No blocker. Full suite green in every review (1130-1140
passed). Coordinator spot-checked F1, F2/F3, F5 against the code at `8f30549`: confirmed.
Production has `/usr/bin/timeout`, so F17 is defensive.

## Must fix before merge

| ID | Severity | Sources | Defect | Fix direction |
| --- | --- | --- | --- | --- |
| F1 | major | A-gpt A01, A-claude A03 | `run_signals` recomputes reports only up to `--report-date`; a backfill run later (the rollout step!) leaves later days' New/spikes stale. `core/daily_signals.py:201` | Recompute through the latest completed published day (max of report date and yesterday UTC), as plan Decision 4 says; entity commands already do this. |
| F2 | major | A-gpt A02, A-claude A01 | Merge/alias by entity id builds a selector with the entity's vendor class; vendorless mentions that joined the entity under the `|V| <= 1` rule stay behind; an alias can make an old entity look New. `daily_signals_entities.py:254-266` | An entity-level override must cover all current members of that entity (including vendorless ones) and keep doing so on later reconciliations. |
| F3 | major | A-claude A02, A-gpt A08 | Empty vendor selector is a wildcard: merging/aliasing a `?` (needs_review) entity swallows the separate vendor entities with the same base key (two companies' "Atlas" become one); conflict detection compares exact tuples and misses wildcard overlaps. | Distinct selector value for "vendorless only" (e.g. reserved `?`); overlap-aware conflict refusal. |
| F4 | major | A-gpt A03 | Stored vendor selectors compare literally to the current class key; when a class gains a shorter member (Google DeepMind -> Google) the override silently stops matching. | Resolve stored selector vendors through current equivalence classes (or store a stable vendor identity). Test class growth. |
| F5 | major | B-gpt B01, B-claude B02 | `/` returns 500 for a payload that passes the response model but has `current_7d` with `expected_7d: null` (`f"{None:g}"`); the page only catches SQLAlchemyError/ValueError. `web/app.py:496-501`, `signals_view.py:75-78` | Render-safe trend formatting and catch any exception in the signals block (log type only); regression test. |
| F6 | major | B-gpt B02, B-claude B01 | Rollback order is wrong: downgrade must run with the feature image before the revert is deployed; the old image cannot find `b6d1f0a7c3e5`, deploy stops at `alembic upgrade head`. `docs/daily-signals.md:139-141`, PR description | Exact ordered rollback (stop timers/app -> downgrade with feature image -> deploy old release -> start) or explicitly keep the additive schema and only revert code; same text in plan and PR description. |
| F7 | minor (real-data impact) | A-claude A05 | Grounding does not normalize typographic quotes/dashes; the model often returns ASCII `'` for `’`, so valid novelty quotes and names fail -> New false negatives. `daily_signals_extract.py:157-158, 286-288` | NFKC + quote/dash translation on both sides in `ws()`. |
| F8 | minor | A-claude A06 | Primary cap (2) and entity cap (8) applied before stoplist removal, so a dropped generic entity ("AI") uses a primary slot and demotes a real one. `daily_signals_extract.py:242-255` | Drop stoplisted entries before caps. |
| F9 | minor (SQLite only; PG ids never reused) | A-gpt A05+A06, A-claude A04 | Observation assembly and scope/extraction joins use numeric `article_id` only; on SQLite (no FK pragma, id reuse) a new article inherits old scope rows/evidence. Plan promised (id, hash) identity. | Key observations, coverage and evidence writes by `(article_id, url_canonical_hash)`; ignore rows whose hash no longer matches. Do not change the global SQLite pragma in `storage/db.py`. |
| F10 | minor (latent) | A-gpt A04, A-claude A08 | Newest version chosen among mention rows; an `ok` newer extraction with zero entities does not supersede older mentions. `storage/daily_signals.py:254-262` | Choose newest `ok` extraction from `article_signals` per identity, like `coverage()`. |
| F11 | minor | A-gpt A07, A-claude A07 | A `--retry-skipped` attempt that ends transient/unknown sets `retry_used=True`; the next run replays the old invalid answers and the article stays skipped forever. Content-changed skipped rows also burn the retry. | Do not consume the retry on incomplete attempts; resume the same retry key; compute retry only when the content hash matches. |
| F12 | minor | A-gpt A09 | An article present on several backfill days is dispatched again in the same invocation after a failed attempt (duplicate cost on failures). | Track attempted (article, content hash, version) per invocation. |
| F13 | minor | A-gpt A10 | Tie between equal-frequency token tuples depends on insertion ids (changes `variant_of`). | Total ordering, e.g. `(join(parts), parts)`; test with reallocated ids. |
| F14 | minor | B-claude B03 | Docs say MAX_*/COMPARABLE_FROM can be set in the server `.env`; in production only `AINEWS_DAILY_SIGNALS_ENABLED` reaches the container. | Docs: only ENABLED is passed; use CLI flags for caps (no compose change needed). |
| F15 | minor | B-gpt B03, B-claude B08 | Migration race recovery says "rerun alembic"; that does not finish the interrupted deploy (receipt/image not updated, next job uses the old image). | Docs: rerun the whole deploy with the same target. |
| F16 | minor | B-gpt B04, B-claude B05+B04 | On date change the signals block keeps the previous date while loading, is not refreshed if the digest fetch fails, and shows "not available yet" on 503 instead of "temporarily unavailable". `digest.html` | Clear/mark the block on date change; load signals independently of the digest result; distinct text for errors. |
| F17 | minor | B-gpt B05 | Without `timeout` the signals step has no hard bound, and `docker rm -f` cleanup is unbounded. | If `timeout` is missing, skip signals with a log line and exit 0; bound cleanup with `timeout`. |

## Optional (do if trivial, else record as follow-up)

| ID | Sources | Item |
| --- | --- | --- |
| N1 | B-claude B06 | Substitute `__SIGNALS_CONTENT__` before `__DIGEST_CONTENT__` (or single pass). |
| N2 | B-claude B07 | Locked re-exec trusts inherited `AINEWS_DAILY_JOB_LOCKED`/`REPORT_DATE`; pass the marker as an argument. Manual-env only. |
| N3 | A-gpt notes | Plan lists settings bounds (calls <= 5000, seconds 60..14400) that Settings does not enforce; recompute window is 401 days; month-word handling (March/May) differs from plan text. Align plan text with code or code with plan. |

## Not accepted / no action

None rejected. Hidden-BAD caveat on New (items below the display cap) stays tracked by Phase 7.

## Process

1. Finish Phase 7 first (no code changes during it).
2. Fix F1-F17 test-first (each finding gets a regression test that fails before the fix), N1-N3 if
   trivial. Keep commits grouped (identity/overrides; storage/version/identity; run/retry; web/UI;
   job/docs).
3. Full gate in a clean copy with PostgreSQL; push.
4. Re-run Phase 7 numbers with `--recompute-only` ($0) and update `dry-run.md`.
5. One verification review of the fix diff only (not the whole PR), then coordinator approval.
