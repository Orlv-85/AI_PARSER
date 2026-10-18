# Daily AI Signals

Feature 006 (`.specify/specs/006-daily-ai-signals/`). The block at the top of `/` answers, for one
published digest day: what is new, which stories several publishers covered, what is spiking or rising,
what is cooling, and how many events of each type happened. Everything is computed from stored data;
page loads never call a provider.

## How it works

1. **Scope.** Only articles of the published digest for day D count (digest items matched to articles
   by exact URL, then by canonical URL hash). Digests before `AINEWS_DAILY_SIGNALS_COMPARABLE_FROM`
   (2026-10-10) are history-only: they feed "first seen" but get no snapshot.
2. **Extraction.** One DeepSeek call per in-scope article (`daily-signals-extract-5`): named entities
   with type, vendor, role and an "is new" judgment with a source quote, the main event type and a
   novelty flag. Answers are validated against the article text (names and quotes must occur in it;
   a quote that dates the release before the article clears "new"). Results are cached per article,
   content hash and version.
3. **Evidence and identity.** Every mention is stored as evidence that survives article retention.
   Entities are derived from all evidence by a deterministic reconciliation (normalized keys, vendor
   classes backed by company mentions, packaging families) plus operator overrides.
4. **Snapshots.** At the end of each run, every comparable published day of the last 400 days is
   recomputed in memory and stored when its payload changed.

## What the reader sees (owner decisions OD1-OD7)

- **New**: an entity first seen in our corpus on D that an article of D presents as newly announced
  (model judgment, shown with its quote as "Source says"). Confirmed = at least 2 publishers; early
  signal = 1. Packaging variants of a known model (sizes, quantization, instruct/base) are not New;
  a new named version or a GA release after a preview is. People and "other" are never New. The list
  shows 8 items: confirmed first, then early models, hardware, benchmarks, datasets, techniques,
  companies, products, policies. "History: N complete days." is shown while fewer than 30 complete
  days precede D.
- **Top stories**: clusters of articles about the same event with at least 2 publishers (max 5).
- **Spikes / Rising**: Rising compares the last 7 days with the previous 7 against a volume-adjusted
  expectation; it needs two windows with at least 6 complete days each (earliest D = 2026-10-23).
  Until then the card shows **Spikes**: D's count against the mean of at least 3 complete trailing days
  with at least 10 digest items.
- **Cooling**: only when the windows are usable; collapsed by default.
- **Event chips**: stories per event type (display only).
- Entities with conflicting vendors (`needs_review`) are excluded from New, Rising and spikes.

Thresholds are code constants (`Thresholds` in `src/app/core/daily_signals_compute.py`), recorded in
every snapshot; a change is a code release with a `METHODOLOGY_VERSION` bump.

## Day states and status

- A day is **published** when a digest row exists (it may have 0 items) and **missing** otherwise;
  missing days never count as zero attention.
- **Complete**: no items, or at least 90% of digest items extracted.
- Status: `unavailable` (no snapshot, 0 items or nothing extracted), `partial` (day not complete),
  `building_history` (a section still waits for history), `ready`.

## Running it

The daily job (`scripts/run_daily_digest_job.sh`, timer `ai-news-daily-digest`) runs `daily-publish`
and then, under the same host lock and time budget, `daily-signals` with an outer `timeout`. The digest
alone decides the job result; a signals failure or timeout is logged and ignored.

`AINEWS_DAILY_SIGNALS_ENABLED` (default `false`, set by the owner in the server's private `.env`) gates
paid extraction only. Recompute-only runs and entity commands work with the flag off and without a key.

Every writer must hold the host lock:

```bash
L="flock -w 7200 /tmp/ai-news-auto-update.lock"
C="docker compose -f docker-compose.prod.yml run --rm"

# daily run for one day (normally done by the job)
$L $C app ai-news daily-signals --report-date 2026-10-16

# backfill chunk, oldest day first; repeat while "progress" > 0 and incomplete days remain
$L $C -e AINEWS_DAILY_SIGNALS_ENABLED=true app ai-news daily-signals --report-date 2026-10-16 \
   --backfill-days 75 --max-calls 600 --max-seconds 3000 --max-usd 0.70

# recompute snapshots after a code change (no provider calls, flag not needed)
$L $C app ai-news daily-signals --report-date 2026-10-16 --recompute-only
$L $C app ai-news daily-signals --report-date 2026-10-16 --recompute-only --recompute-all

# one deliberate retry of articles skipped for invalid output
$L $C -e AINEWS_DAILY_SIGNALS_ENABLED=true app ai-news daily-signals --report-date 2026-10-16 \
   --retry-skipped
```

`ai-news daily-signals` options: `--report-date` (default yesterday UTC; completed days only),
`--backfill-days N` (1-800), `--max-calls`, `--max-seconds`, `--max-usd` (override the
`AINEWS_DAILY_SIGNALS_MAX_*` settings for this run), `--cache-dir` (default `data/daily-signals`),
`--recompute-only`, `--recompute-all`, `--retry-skipped`. It prints one JSON line and exits 0 for every
documented state (`ok`, `disabled`, `missing_provider_key`, `recompute_only`, `cap_reached`,
`deadline_reached`, `provider_unavailable`, `usage_exceeded_bound`); 1 means an unexpected error.

## Cost and limits

- About $0.0009 per article (measured in the prompt gate); a typical day of 60-90 articles costs
  $0.05-0.08.
- Per-run caps, checked before every provider call with a reservation: calls
  (`AINEWS_DAILY_SIGNALS_MAX_CALLS`, 200), USD (`AINEWS_DAILY_SIGNALS_MAX_USD`, 0.50) and an app-side
  deadline (`AINEWS_DAILY_SIGNALS_MAX_SECONDS`, 2700; no call starts with less than 95 s left).
  Three consecutive failed attempts stop the run.
- The ledger `data/daily-signals/ledger.sqlite3` (mode 0600) records every physical call; a saved 200
  answer is replayed instead of paid again. Each paid run writes
  `data/daily-signals/runs/<run_id>.json` (no key, no article text).
- Budgets across several invocations (validation, backfill) are tracked by the operator: pass the
  remaining budget as `--max-usd` and add up `run.usd` from the run reports.

## Fixing entities

All commands store an override, re-run reconciliation and recompute snapshots; no provider calls.

```bash
# entities needing a decision (conflicting vendors)
docker compose -f docker-compose.prod.yml exec db psql -U ainews -d ainews \
  -c "select id, display_name, entity_key from ai_entities where needs_review and active"

$L $C app ai-news daily-signals-entities merge --source 41 --target 17
$L $C app ai-news daily-signals-entities alias --entity 17 --name "GPT-6 Astra"
$L $C app ai-news daily-signals-entities overrides
$L $C app ai-news daily-signals-entities overrides --delete 3
$L $C app ai-news daily-signals-entities purge-evidence --article 98123
```

- `merge` and `alias` select mentions by stable keys, not by entity id, so they survive re-extraction
  and a vendor appearing later. A selector already owned by another override is refused.
- `purge-evidence` removes the stored evidence of an article that no longer exists (for example
  after non-news cleanup); it refuses for existing articles.

## Retention and cleanup

- `article_signals` and `daily_signal_scope` reference `articles` with `ON DELETE CASCADE`; prune
  and cleanup delete them with the article. `signal_mentions` has no foreign key and keeps the evidence,
  so "first seen" does not move when old articles are pruned.
- The legacy cleanup guard accepts exactly these two cascade foreign keys; any other new reference to
  `articles` still stops it.
- Signals are derived data and are not in the cleanup export: restoring articles does not restore
  extractions; re-extraction costs provider calls.
- On SQLite (local) foreign keys are not enforced; loaders join `articles`, so orphans are ignored.

## Rollback

Set `AINEWS_DAILY_SIGNALS_ENABLED=false` (stops paid work), revert the UI commit, or revert the
feature and run `alembic downgrade a42b750d0c44` with the app and jobs stopped. Digest, articles and
weekly data are never written by signals.

## Not in the first release

Ledger budget ids, per-day spend caps, per-article attempt limits and `reset-attempts`, the watchdog
thread, the `split` override, stored duplicate candidates with `suspects`/`dismiss`. Each comes back
when its trigger in the plan ("Deferred (not in first release)") occurs.
