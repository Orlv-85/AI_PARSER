# PR #39 - Independent review A (GPT), 2026-10-18

**Verdict: merge after fixes.** Ten confirmed defects: seven major, three minor. The existing tests are green, but miss important identity, override and resume transitions.

**SHA reviewed:** `8f30549a07225b17d1f8a7187b1d4956b174ecb6`.
**PR:** #39, `feat/006-daily-ai-signals` -> `master`.
**Worktree:** `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER-review-a-gpt` (detached, retained).
**Scope:** data path, extraction, reconciliation, computation, persistence/migration, ledger, CLI and cleanup FK guard. No other reviewers' report files were read; the requested Phase A coordinator review was read.

## Validation

All commands ran from the detached worktree, without `.env`, using the main repository's Python 3.14 virtualenv and `PYTHONPATH=src`. No application source or existing tests were changed. The worktree was clean after validation. Reproduction scripts were kept in writable `/private/tmp` and executed from the worktree; this report is the only file written in the main checkout.

| Check | Result |
| --- | --- |
| New tests: `test_daily_signals_{compute,entities,extract,ledger,migration,repo,run}.py`, `test_cli_daily_signals.py`, `test_web_daily_signals_api.py` | 182 passed; exit 0 |
| Full repository suite, run once with local test PostgreSQL | **1140 passed in 50.84s**, no skips; exit 0 |
| Independent defect reproductions, final run of `/private/tmp/test_pr39_review_a.py` | **10 passed in 0.90s**; these assertions confirm the incorrect current behavior, not correctness |
| Independent PostgreSQL migration check, `/private/tmp/test_pr39_review_a_pg.py` | **1 passed in 1.25s** |

Full-suite command:

```sh
rtk proxy /Users/vyacheslavorlovskiy/.codex/bin/run-pytest \
  --python /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python \
  --env PYTHONPATH=src \
  --env AINEWS_TEST_POSTGRES_URL=postgresql+psycopg://ainews_test:isolated_ci_test@127.0.0.1:55432/ainews_test \
  -- -o addopts='' -q -p no:cacheprovider
```

The PostgreSQL endpoint was the existing local `ainews-pg-test` container (`postgres:18-alpine`). Integration tests use isolated schemas. The independent migration check used a unique `review_a_<uuid>` schema, then removed that schema only. It exercised the new migration's `upgrade`/`downgrade` functions through Alembic Operations, rather than claiming an additional full-chain PostgreSQL Alembic run.

Reproduction commands (same worktree):

```sh
rtk proxy /Users/vyacheslavorlovskiy/.codex/bin/run-pytest \
  --python /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python \
  --env PYTHONPATH=src \
  -- /private/tmp/test_pr39_review_a.py -o addopts='' -q -s -p no:cacheprovider

rtk proxy /Users/vyacheslavorlovskiy/.codex/bin/run-pytest \
  --python /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python \
  --env PYTHONPATH=src \
  -- /private/tmp/test_pr39_review_a_pg.py -o addopts='' -q -s -p no:cacheprovider
```

No provider calls, production access, remote writes, commits, pushes or PR comments. Provider paths were exercised with `httpx.MockTransport`. `make lint` was not run: this was a read-only review with no code changes or commit. Phase 7 paid history validation was not run and remains outside this review.

## Findings

Locations below refer to the reviewed SHA in the retained worktree. Severity: major = incorrect stored/displayed signals or broken operator recovery; minor = narrower correctness or efficiency issue. No blocker-level defect was established.

| ID | Severity | File:line | Defect | Concrete failure scenario | Evidence | Suggested fix | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A01 | major | `src/app/core/daily_signals.py:201`; `src/app/storage/daily_signals.py:472` | A historical run reconciles all entities but does not refresh affected later snapshots. | A 10-16 report lists Atlas as New; add/extract Atlas history for 10-14 and run signals with `--report-date 2026-10-14`. The entity's first_seen moves to 10-14, but the stored 10-16 report still says New. `--recompute-all` removes only the lower date bound and does not fix the upper bound. | `HISTORICAL_RUN 2026-10-14 ['Atlas'] ['2026-10-14']`; an explicit subsequent recompute through 10-16 removes Atlas. | Separate extraction target date from recompute horizon; recompute through the latest completed published day as Decision 4 requires. | confirmed |
| A02 | major | `src/app/core/daily_signals.py:232`; `src/app/core/daily_signals_entities.py:254` | Merge by entity ID leaves that entity's vendor-less members behind. | Atlas has one Acme mention and one vendor-less mention; automatic reconciliation assigns both to the same entity. Merging its ID into Bravo records vendor selector `acme`. The vendor-less Atlas mention has `keys.vendor_key == ''`, so it does not match and becomes a separate Atlas entity again. | `PARTIAL_MERGE acme ['auto:artifact:atlas', 'auto:org:acme', 'manual:1']`; reproduction calls the actual `merge_entities` operator function. | Apply an entity merge to all members assigned to the selected entity, including automatically absorbed vendor-less mentions; preserve this membership rule on later reconciliation. | confirmed |
| A03 | major | `src/app/core/daily_signals_entities.py:207`; `src/app/core/daily_signals_entities.py:255` | Persisted vendor selectors silently stop matching when a vendor class gains a shorter equivalent name. | Merge Atlas/Google DeepMind into Bravo, recording `googledeepmind`. Later a different article introduces vendor Google and a Google company mention. The class becomes `google`, but the saved selector is compared literally to it, so Atlas escapes the merge. | `VENDOR_SELECTOR manual:1 auto:artifact:atlas`. This needs only normal new evidence, not edits to the override. | Resolve stored vendor selectors through the current equivalence classes, or persist stable vendor identities; test class growth as well as first appearance of a vendor. | confirmed |
| A04 | major | `src/app/storage/daily_signals.py:254` | An empty successful extraction in a newer version cannot supersede older mention evidence. | v1 contains Atlas; v2 succeeds with `entities: []`, event `other`. `load_evidence()` discovers versions only from mention rows, so it selects v1. Coverage and event selection use the successful v2 extraction, producing a snapshot with v2's event and v1's false Atlas novelty. | `EMPTY_VERSION ['Atlas'] {'https://a.com/x': 'other'}`. Version order is monkeypatched to `(v1, v2)`, as in the existing versioning tests. | Choose the newest successful extraction independently of whether it has mentions; retain an empty-version marker across article deletion so old evidence cannot reappear after retention. | confirmed |
| A05 | major | `src/app/storage/daily_signals.py:400`; `src/app/storage/daily_signals.py:423` | Observation assembly drops the URL hash from article identity and attaches retained evidence to a different article with the same ID. | Delete article id 1 with Atlas evidence on D, insert a new id 1 with another canonical hash and Bravo on D. Even with SQLite FK enforcement ON, both mentions are attached to the new live article. Atlas is displayed with the new article's URL and its old novelty quote. | `ID_REUSE ['Atlas', 'Bravo'] [('Atlas', 'https://new.com/x'), ('Bravo', 'https://new.com/x')]`. The retained rows themselves are correctly separated by hash; the error occurs when building observations. | Key observation evidence by `(article_id, url_canonical_hash, scope_day)` and join only the live identity. Keep deleted identities for first-seen evidence, not current article observations. | confirmed |
| A06 | major | `src/app/storage/daily_signals.py:189`; `src/app/storage/daily_signals.py:147`; `src/app/storage/models_sql.py:456` | With the application's default SQLite FK setting, orphan scope rows become memberships of a new article that reuses the ID. | SQLite connections created by `storage/db.py` do not enable `foreign_keys`. Delete an old article, reuse its ID for a new article on D, and extract it. The old scope survives; `save_extraction()` inserts the new entity's evidence into every scope for the numeric ID, including the old day. The new entity is falsely treated as previously known. | `SQLITE_ORPHAN 2026-10-14 ['https://new.com/x']` for a new article published in the 10-16 digest. Unlike A05, this corrupts stored first_seen evidence even across different days. | Ensure derived-row deletion on supported SQLite connections, including existing orphans, or store/check full article identity in scope/extraction rows. An inner join on numeric ID alone does not protect against ID reuse. | confirmed |
| A07 | major | `src/app/core/daily_signals.py:98`; `src/app/core/daily_signals.py:135` | A transient failure during `--retry-skipped` permanently abandons the retry request and replays the original invalid answers on resume. | Base and recovery return invalid JSON, giving `skipped`. Operator retries; retry POST gets 503, storing `failed, retry_used=True`. On the next run, retry mode is selected only for `skipped && !retry_used`, so the code replays the original base/recovery cache and returns to permanently skipped without contacting the now-healthy provider. | `RETRY_RESUME skipped True 0 {'replayed': 2, 'skipped': 1}`. | Persist the active attempt mode separately from terminal retry exhaustion; resume the same retry/recovery keys after transient/unknown outcomes without granting a second deliberate retry. | confirmed |
| A08 | minor | `src/app/core/daily_signals_entities.py:350` | Override conflict detection compares exact tuples although an empty vendor selector is a wildcard. | Save merge `Atlas/acme -> Bravo`, then alias `Atlas/* -> Charlie`. Both overrides are accepted, although they own overlapping mentions and different targets. Alias precedence silently redirects Atlas away from the first override. | `OVERLAP manual:1 manual:2 {1: 'manual:2', 3: 'manual:2', 2: 'auto:org:acme'}`. | Detect selector overlap when either vendor is empty, including source/target overlaps; reject conflicting manual targets before writing. | confirmed |
| A09 | minor | `src/app/core/daily_signals.py:129` | An article appearing in multiple backfill days is physically attempted again in the same invocation after an incomplete attempt. | The same article is in D-1 and D. Its first call gets 503. The failed row remains pending; the day loop reaches it again and dispatches the identical body a second time instead of leaving it for a later run. Unknown outcomes follow the same path and may incur duplicate cost. | `DUPLICATE_ATTEMPT 2 {'attempt_transient': 2, 'dispatched': 2, 'pending': 2}`; both captured request bodies are equal. Per-run caps still hold. | Track attempted article identity/content/version for the invocation across scope days; keep schema recovery inside that one article attempt. | confirmed |
| A10 | minor | `src/app/core/daily_signals_entities.py:318` | A tied base-token choice depends on insertion IDs and changes `variant_of`. | Equal-frequency `Muse Spark` and `MuseSpark` share the same normalized key. Their `join` tie-breakers are equal, so the first encountered token tuple wins. Reversing their assigned mention IDs changes whether `Muse Spark Open` has that older entity as a token-prefix relative. | `ARRIVAL_TIE ('muse', 'spark') ('musespark',) [True, False]`. | Use a total ordering for token-tuple ties, e.g. `(join(parts), parts)`; test reallocated insertion IDs, not only shuffling a list with fixed IDs. | confirmed |

## Reproduction details and test gaps

The scratch reproductions use small in-memory SQLite databases, the repository's existing seed/extraction helpers, and mocked HTTP responses. Except A06, SQLite storage reproductions explicitly enable `PRAGMA foreign_keys=ON`, so A05 is not explained away by missing cascades. A06 intentionally matches the application's default SQLite connection setup. No production data is needed.

| Finding | Reproduction function in `/private/tmp/test_pr39_review_a.py` | Why existing tests miss it |
| --- | --- | --- |
| A01 | `test_historical_run_leaves_future_snapshot_stale` | Repo tests manually call `recompute_reports(D)` after modifying older evidence; they do not drive the historical run's narrower upper bound. |
| A02 | `test_merge_by_entity_id_leaves_vendorless_members_behind` | Existing override tests do not merge an entity containing both explicit-vendor and automatically absorbed vendor-less members through its actual ID. |
| A03 | `test_vendor_class_growth_invalidates_override` | `test_merge_survives_vendor_and_reextraction` starts with a wildcard vendor selector; it does not test an already-populated selector whose class name changes. |
| A04 | `test_empty_new_version_resurrects_old_mentions` | `test_evidence_uses_newest_ok_version_with_fallback` gives the new version a nonempty entity list. |
| A05 | `test_reused_id_leaks_deleted_mentions_into_new_article` | `test_reused_article_id_leaves_old_evidence` asserts that both hash-separated rows survive, but never computes the resulting snapshot or checks its links. |
| A06 | `test_sqlite_orphan_membership_rebinds_to_reused_id` | The repo test fixture enables SQLite foreign keys, unlike `storage/db.py`; retention tests therefore do not exercise default runtime semantics. |
| A07 | `test_retry_transient_cannot_resume` | Retry tests cover terminal invalid outputs; outage tests cover initial extraction. Neither crosses retry mode with a transient response and restart. |
| A08 | `test_wildcard_override_conflict_accepted` | Conflict tests use identical vendor selectors, not wildcard overlap. |
| A09 | `test_same_article_attempted_twice_in_same_run` | Backfill tests seed distinct articles per date; one-call tests use one digest date. |
| A10 | `test_token_tie_depends_on_arrival_ids` | Pure-function permutation tests retain mention IDs; the storage insertion-order test checks first_seen only. |

Final reproduction output:

```text
ID_REUSE ['Atlas', 'Bravo'] [('Atlas', 'https://new.com/x'), ('Bravo', 'https://new.com/x')]
EMPTY_VERSION ['Atlas'] {'https://a.com/x': 'other'}
HISTORICAL_RUN 2026-10-14 ['Atlas'] ['2026-10-14']
RETRY_RESUME skipped True 0 {'replayed': 2, 'skipped': 1}
OVERLAP manual:1 manual:2 {1: 'manual:2', 3: 'manual:2', 2: 'auto:org:acme'}
VENDOR_SELECTOR manual:1 auto:artifact:atlas
PARTIAL_MERGE acme ['auto:artifact:atlas', 'auto:org:acme', 'manual:1']
ARRIVAL_TIE ('muse', 'spark') ('musespark',) [True, False]
DUPLICATE_ATTEMPT 2 {'attempt_transient': 2, 'dispatched': 2, 'pending': 2}
SQLITE_ORPHAN 2026-10-14 ['https://new.com/x']
10 passed in 0.90s
```

## Plan/spec comparison

The review uses final plan revision 6 and its accepted SD1-SD13/C2 decisions, not superseded requirements for budget IDs, lifetime attempt limits, split overrides, an 80-second watchdog, interactive event chips or legacy snapshots.

- A01 violates Decision 4's recompute through the latest completed day after history changes.
- A02/A03/A08 violate Decision 2's operator merge semantics, stable selectors and conflict refusal.
- A04 violates Decision 4/SD12's newest-successful-version evidence selection, including empty results.
- A05/A06 violate Decision 4's `(article_id, url_canonical_hash)` identity and ID-reuse isolation.
- A07 violates Decision 1's resumable pending outcomes for transient/unknown responses.
- A09 differs from Decision 1's retry by a later run and T3.3's one dispatch per pending article; schema recovery is a separate, intentional exception.
- A10 violates the promised independence from arrival/backfill order, although it does not change the normalized entity key in this example.

Additional low-impact drift observed, not promoted to findings: the plan appendix lists settings upper bounds of 5,000 calls/14,400 seconds and a 60-second minimum, while Settings uses only `ge=1`; recompute includes `until - 400` through `until` (401 dates); the retrospective code treats both March and May as ambiguous month words, whereas Decision 1 explicitly special-cases May only. These do not establish a spending-cap bypass or a merge blocker.

## Verified OK

- **Ledger caps/accounting under the documented assumptions:** reservation and cap check occur in the same `BEGIN IMMEDIATE` transaction before dispatch; one physical POST per `dispatch`; known usage replaces the reservation, unknown usage retains it; explicit overload-only responses cost zero in the estimate; three failures stop subsequent dispatch; successful 200 responses replay without POST. No per-run cap bypass was established. Actual usage above the assumed reservation stops subsequent calls, as explicitly designed; this is not a guarantee against a provider billing beyond the assumed bound. No external price verification was performed.
- **Recovery bodies and input validation:** base/recovery/retry bodies differ; untrusted source is JSON data under the system prompt; model/finish/schema validation, enum coercion, grounding, quote bounds, primary/entity caps and duplicate merging match the main plan rules. Unsupported names are dropped. Retrospective cases with null publication date are covered. The known syntactic acceptance of instruction-shaped novelty quotes is explicitly acknowledged by the plan, not presented here as a new security defect.
- **Core normalization and normal reconciliation:** version and numeric separators, company suffixes, org-backed vendor stripping, no digit-leading stripped remainder, packaging tokens, preview/beta preservation, type groups, vendor aliases and shared ambiguous `?` entities have meaningful tests. Fixed-input ordering is stable, subject to A10's arrival-ID tie.
- **Snapshot gates and counts:** New requires primary plus supported novelty in the same article; old-family suppression and same-day variants, confirmed/early ordering, distinct-publisher links, strict-majority clustering, event-family boundaries and the pinned multi-publisher fixture stories pass. Null `published_at` ordering is explicitly tested. Rising/Cooling use complete days, volume-adjusted expectations, minimum support and zero-denominator checks; missing days are excluded and observed-empty days are usable zeros. Status precedence and section readiness match the revised plan.
- **Idempotence with unchanged data:** generated_at is excluded from the hash; emitted floats are rounded; unchanged reports are not rewritten; reconciliation updates derived rows only when attributes change. Synthetic 60-day test observed approximately 0.65s first recompute / 0.55s unchanged recompute during the full run. This is not a new full-year benchmark.
- **Migration and PostgreSQL retention:** SQLite migration tests cover previous-head upgrade, schema parity with models, create_all-before-upgrade, downgrade and pre-feature rows. Independent PostgreSQL check confirmed guarded/repeated upgrade, create_all compatibility, downgrade and CASCADE: after deleting the parent article, counts were `[article_signals=0, daily_signal_scope=0, signal_mentions=1]`. Nullable vendor display fields are not part of the relevant unique identity constraints; override selector vendor columns are non-null. A06 remains a separate default-SQLite runtime problem.
- **Transactions and uniqueness:** per-article commits, rollback on ledger stop, report insert savepoint/IntegrityError retry and exact duplicate override refusal are covered. The wildcard conflict in A08 is above the SQL uniqueness layer. The documented requirement to serialize writers under the host lock and the accepted create_all/migration race remain assumptions.
- **Cleanup guard:** the new direct-FK allow-list is restricted to `article_signals`/`daily_signal_scope`, constrained column `article_id`, and `ON DELETE CASCADE`. Other direct tables and non-cascade derived FKs remain rejected by tests, including the PostgreSQL unknown-table test. No concrete unsafe direct FK accepted by the current migrated schema was found; this is not a claim that arbitrary transitive dependencies are audited.
- **CLI and paid-work gate:** completed UTC dates, oldest-first backfill, max-call/time/USD options, default disabled behavior, missing-key behavior, recompute-only and entity commands without provider calls are tested. Digest data remains unchanged in orchestration tests. A01/A07/A09 identify gaps beyond the normal paths.

## Remaining release condition

Fix the seven major defects and add regression coverage for the transitions above before merging; address the three minor defects as part of that pass if practical. Preserve the existing Phase 7 history-quality gate: the cached five-day remeasurement is useful evidence, but this independent review did not validate the full extracted-history corpus or real-world precision/recall. The green 1140-test suite alone does not satisfy that product-quality gate.

**Final verdict: merge after fixes.**
