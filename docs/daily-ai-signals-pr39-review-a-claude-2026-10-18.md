# PR #39 independent review A (claude) - data path, storage, money (2026-10-18)

- Reviewer: Claude (Opus 5.5), read-only, worktree `../AI_PARSER-review-a-claude` (detached).
- SHA reviewed: `8f30549a07225b17d1f8a7187b1d4956b174ecb6` (PR head from `gh pr view 39`).
- Read: `AGENTS.md`, spec 006 `plan.md` (rev 6), the code in scope, the new tests. Other reviewers'
  reports were not read.
- Environment: `PYTHONPATH=src`, `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1`, no `.env` in
  the worktree, no network, no provider calls.

What I ran and the results:

| Command | Result |
| --- | --- |
| `pytest -o addopts="" -q tests/unit/test_daily_signals_*.py tests/unit/test_cli_daily_signals.py tests/unit/test_legacy_cleanup.py tests/unit/test_web_daily_signals_api.py` | 207 passed |
| `pytest -o addopts="" -q` (full suite) | 1130 passed, 10 skipped (PostgreSQL integration tests, no DSN) |
| `python -m ruff check src tests` | All checks passed |
| Proof scripts (scratchpad, not committed): `merge_split.py`, `review_q.py`, `misc.py` | Output quoted below |

Not run: `make lint` (mypy/pylint), PostgreSQL tests (`tests/integration/test_legacy_cleanup_postgres.py`),
and Alembic upgrade/downgrade on PostgreSQL.

## Findings

| ID | Severity | File:line | Defect | Failure scenario | Evidence | Suggested fix | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A01 | major | `src/app/core/daily_signals_entities.py:254-266`, `src/app/core/daily_signals.py:232` | A merge or alias selector built from an entity with a vendor class (`entity.vendor_class`) matches only mentions whose `vendor_key` equals that class. The entity's vendorless mentions, which joined it under the `\|V\| <= 1` rule, are left behind. | Evidence: org "Reflection AI"; "Reflection Beam" (vendor Reflection AI, D=10-16); "Beam" without a vendor on 10-05 and 10-16. All of them form one entity, `auto:artifact:beam` (class `reflection`, first seen 10-05). (a) `merge --source beam --target atlas` moves only mention 2; `auto:artifact:beam` stays with the vendorless mentions. (b) `alias --entity beam --name ...` creates `manual:1` with mention 2 only, so its first_seen becomes 10-16. If that mention is primary and `is_new`, the alias turns Beam into a **false New** on 10-16. | `merge_split.py`: before `{'auto:artifact:beam': ('reflection', '2026-10-05')}`; after merge `{2: 'manual:1', 3: 'auto:artifact:beam', 4: 'auto:artifact:beam', 5: 'manual:1'}`; after alias `{2: 'manual:1', 3: 'auto:artifact:beam', 4: 'auto:artifact:beam', 5: 'auto:artifact:atlas'}` | Make the selector cover what the entity actually holds. For an `auto:<g>:<base>` key (no class suffix), store an "any vendor" selector, or `vendor_class` plus "and vendorless". Use the explicit class only for `auto:<g>:<base>:<class>` keys. Add tests with a non-empty vendor class. | confirmed |
| A02 | major | same as A01 | The selector of a needs-review entity `auto:<g>:<base>:?` has `vendor_class == ""`, and `vendor_ok("")` matches **every** vendor class. Merging or aliasing the `?` entity, which is the natural operator action to resolve it, also swallows the separate vendor entities with the same base key. | OpenAI "Atlas", Google "Atlas" and two vendorless "Atlas" mentions give `atlas:openai`, `atlas:google` and `atlas:?`. Merging `atlas:?` into "Atlas Pro" assigns all four Atlas mentions to `manual:1`, which merges two different companies' products. | `review_q.py`: `{3: 'manual:1', 4: 'manual:1', 5: 'manual:1', 6: 'manual:1'}` (3 = OpenAI Atlas, 4 = Google Atlas) | Give `?` entities a selector that matches vendorless mentions only, e.g. a reserved class value `?` that `_override_target` compares as "vendor_key == ''". | confirmed |
| A03 | minor | `src/app/core/daily_signals.py:201` | Plan Decision 4 says to recompute "from comparable_from to the latest completed day". The run recomputes only up to `options.report_date`. | Backfill `--report-date 2026-10-16 --backfill-days 60`, run on 10-19 after 10-17 and 10-18 are published. Evidence added for earlier days can move first_seen earlier, but the stored 10-17 and 10-18 reports (New, spikes) stay stale until the next daily run. The API serves them meanwhile. | Code: `repo.recompute_reports(options.report_date, all_days=...)`. The entity commands already use yesterday (`cli/main.py`, `_entity_command`). | Pass `max(report_date, yesterday UTC)` (or the latest published day) as `until`. | confirmed (code) |
| A04 | minor | `src/app/storage/daily_signals.py:207-216, 375-388, 416-420` | The app never enables `PRAGMA foreign_keys` on SQLite, so CASCADE does not run there. `article_signals` and `daily_signal_scope` rows of a deleted article become orphans. A new article that reuses the id (SQLite reuses max rowid + 1) inherits them. | Article 1 extracted on 10-14 ("Atlas"), then deleted (prune / cleanup). A new article reuses id 1 and appears in the 10-16 digest. Without any extraction, coverage counts it as extracted. The old payload is written as its evidence, and the new article (old URL) shows up in 10-14 observations. A later re-extraction writes its evidence on 10-14 too, so first_seen moves to 10-14 and suppresses New on 10-16. | `misc.py` part 1: `coverage D2 extracted: 1 of 1`; `evidence of new article: [('2026-10-16','atlas',True), ...]`; `D1 observations now contain: [(1, 'https://a.com/old')]`. The repo tests set `PRAGMA foreign_keys=ON` (`tests/unit/test_daily_signals_repo.py:36`), so they do not model the app. | Local/dev only (PostgreSQL enforces CASCADE). Either delete signals rows explicitly in prune and cleanup, or filter `article_signals` by `content_hash`/identity and scope by URL hash. At minimum, note it in `docs/daily-signals.md`. | confirmed |
| A05 | minor | `src/app/core/daily_signals_extract.py:157-158, 286-288` | Grounding (`ws`) does not normalize typographic quotes or dashes. The user message is `encoded()` with `ensure_ascii=True`, so the model sees `’` escapes and may answer with an ASCII `'`. Such a quote fails the substring check. | Article "Acme's new model Atlas launched today." with a curly apostrophe, and a model quote with an ASCII `'`. Result: `is_new=False`, `novelty_unsupported`, so New gets a false negative. Names containing apostrophes or dashes (e.g. "Llama-3 – Instruct") hit the same check. | `misc.py` part 2: `is_new: False rejects: {'novelty_unsupported': 1}` | In `ws()`, apply NFKC plus the same quote/dash translation on both sides (`daily_signals_entities.QUOTES` plus dashes). It is cheap and makes the check symmetric. | confirmed (how often: plausible) |
| A06 | minor | `src/app/core/daily_signals_extract.py:242-255` | The primary cap (2) and the entity cap (8) run before rule 8 drops stoplisted entries, so a dropped generic entity uses up a slot. | Response with primaries `AI` (technology), `Acme`, `Atlas`. `Atlas` is demoted to `mentioned`, then `AI` is dropped as stoplisted, so the article has one primary. The demotion affects New eligibility (needs primary) and clustering edges. | `misc.py` part 3: `[('Acme', 'primary'), ('Atlas', 'mentioned')] {'primary_capped': 1, 'stoplisted': 1}` | Drop stoplisted entries before applying rules 7 and 8a (it does not change the request or the cache). | confirmed |
| A07 | minor | `src/app/core/daily_signals.py:96-101, 134-136` | When a `--retry-skipped` attempt ends `unknown`/`transient`, `save_failure(status="failed", retry_used=True)` runs. The next normal run sees `failed` and sends the **base** body, which replays the saved invalid answers at no cost and re-skips the article. The one allowed retry is spent without ever getting a provider answer. Also, a `skipped` row whose content changed is retried with the retry body and consumes `retry_used`. | Operator retries a skipped article during an outage. Afterwards the article is permanently `skipped` with no retry path short of a version bump. | Code reading. | Do not set `retry_used` for an incomplete attempt, or keep `status="skipped"` and add a separate pending marker. Compute `retry` only when `row.content_hash == content_hash`. | plausible |
| A08 | nit | `src/app/storage/daily_signals.py:254-262` | The evidence set takes the newest version **among stored mention rows**. An `ok` extraction in a newer version with `entities: []` writes no rows, so the older version's rows are used. The plan says to use the newest version with an `ok` extraction. | After a version bump, an article re-extracted to zero entities keeps contributing its old mentions (first_seen, counts). Latent while `EXTRACTION_VERSIONS` has one entry. | Code: `newest` is computed from `SignalMention` rows only. | Compute `newest` from `ArticleSignal(status='ok')` per identity, the same way `coverage()` does. | confirmed (latent) |
| A09 | nit | tests | The tests miss the risky cases above: override tests use only `vendor_class=""` (`test_daily_signals_entities.py:280-322`, `test_daily_signals_repo.py:222`); the repo fixture enables FK enforcement unlike the app; no test recomputes after a backfill that ends before the latest day; no test covers a retry that ends incomplete. | - | - | Add regression tests together with A01-A07. | confirmed |

## Verified OK

- **Reconciliation purity and order independence**: `reconcile` depends only on the evidence set and
  the overrides. Vendor classes use sorted union-find with the shortest/lexicographic key, ties are
  deterministic (`_ranked`, `TYPE_ORDER`), and overrides are applied in id order. The shuffled-input
  test is meaningful. Org backing (CP1 finding 5) and stripping of a leading digit or stoplisted
  remainder match the plan.
- **Keys**: `join` digit-hyphen rule, the company suffix rule, the packaging regex and family
  trimming match plan rules 1-8 (`v1` != `v1.1`, `7B` != `70B`, preview/beta not packaging).
- **Extraction**: the body is exactly as in the plan. Recovery and retry suffixes give distinct
  request keys, so a saved invalid answer is never retried by replay. Whole-response validation
  (model, `finish_reason`, JSON types incl. `bool` for `novelty_claim`) works; `None` content gives
  `extraction_schema`. Names are grounded; canonical and vendor fall back. The retrospective rule
  matches 5a (ambiguous May/March, year taken from an adjacent number, later month without a year
  ignored). Article text is only data: output is typed, length-bounded and escaped.
- **Ledger / money**: exactly one POST per `dispatch`; replay only for `state='response' AND
  status_code=200`. Calls, USD (actual or reservation) and deadline (95 s reserve) are checked inside
  `BEGIN IMMEDIATE` together with the `reserved` insert, so a run cannot start a POST past its caps.
  The reservation bounds actual cost (bytes >= tokens, +2048 for template overhead,
  `max_tokens` x output price). If it were ever exceeded, `usage_exceeded_bound` stops the run.
  Rows left `reserved` by a crash become `unknown` and count at the reservation. After 3 consecutive
  `unknown`/`transient`/`error_billed` results the run stops. The key is not stored. The deadline
  uses the same monotonic clock as `started`. The 60 s body deadline is checked between chunks, and
  the 20 s read timeout bounds a stalled stream.
- **Run flow**: `LedgerStop` rolls back only the current article; snapshots are still recomputed.
  Commit per article. The flag gates only paid extraction (`--recompute-only` and entity commands
  run with the flag off and no key). Backfill runs oldest first. Max one base call plus one recovery
  call per article per run. `--max-usd` is validated (`microdollars`) in the CLI and in settings.
- **Compute**: New gate (primary + `is_new` with quote, `first_seen == D`, person/other/`?`
  excluded, family suppression against older families); confirmed/early ordering (CP1 finding 6).
  Spikes use only complete comparable trailing days with >= 10 items and a mean floor of 1/3.
  Windows require min(prev) >= comparable_from, >= 6 complete days each and non-zero `N`, so there
  is no division by zero. Status precedence matches the plan. Floats are rounded to 3 decimals and
  `generated_at` is excluded from the hash. Null `published_at` sorts last; ties go by article id.
  Clustering requires a strict majority.
- **Storage**: the UNIQUE keys contain no nullable columns (`vendor_key` is non-null). Duplicate
  mention keys are deduplicated before insert. Membership replacement and re-extraction replace
  evidence only for existing identities `(id, url_canonical_hash)`. Evidence of deleted articles
  survives until `purge-evidence`, which refuses for existing articles. The `save_report`
  IntegrityError path uses a savepoint and then updates. Recompute rewrites only reports whose hash
  changed. Coverage counts digest items (unmatched included) and joins `articles`.
- **Migration**: tables, column nullability, unique constraints and index names match `create_all()`
  (also covered by `test_daily_signals_migration.py`). Each create is skipped if present; downgrade
  drops only the six new tables. Checked on SQLite only.
- **`legacy_cleanup` guard**: it accepts only `article_aliases.article_id` and the two named derived
  tables when their FK is `article_id` with `ON DELETE CASCADE`. Any other FK to `articles` (other
  table, other column, or no CASCADE on these tables) still raises, so it does not hide an unknown
  unsafe FK. On PostgreSQL, cleanup deletes the paid extractions by cascade, which the plan accepts.
- **CLI**: `--report-date` must be a completed UTC day; caps fall back to settings; `--backfill-days`
  is limited to 1..800; entity commands roll back and exit 1 on refusal.

## Verdict

**Merge after fixes.** A01 and A02 are confirmed identity defects in the operator merge/alias commands.
They can create false New items or merge different vendors' products, but they only trigger when an
operator runs `daily-signals-entities merge/alias`, never in the automatic daily path. Fix them, with
tests, before operators are told to use overrides. A03-A07 are small, low-risk fixes and can go in the
same change. A08 and A09 can follow. The money/ledger path, extraction validation, reconciliation
purity, compute determinism and the migration have no blocking issues.
