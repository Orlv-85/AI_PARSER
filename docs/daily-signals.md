# Daily AI Signals

Feature 006 (`specs/006-daily-ai-signals/`), iteration 2 in 007
(`specs/007-daily-signals-brief/`: brief, one-liners, noise rules). The block at the top of `/` answers, for one
published digest day: what is new, which stories several publishers covered, what is spiking or rising,
what is cooling, and how many events of each type happened. Everything is computed from stored data;
page loads never call a provider.

How it works (scope, sections, New rules, spikes, brief, day states) and why: the feature doc next to
the code, `src/app/core/daily/signals.md`. This guide is for operators only.

## Running it

The daily job (`scripts/run_daily_digest_job.sh`, timer `ai-news-daily-digest`) runs `daily-publish`
and then, under the same host lock and time budget, `daily-signals` with an outer `timeout`. The digest
alone decides the job result; a signals failure or timeout is logged and ignored.

`AINEWS_DAILY_SIGNALS_ENABLED` gates paid extraction only. The application default is `false` (local
runs stay free); `docker-compose.prod.yml` defaults it to `true` in production, so
`AINEWS_DAILY_SIGNALS_ENABLED=false` in the server's private `.env` is the kill switch. Recompute-only runs and entity commands work with the flag off and without a key.
In production it is the only signals setting that reaches the container (`docker-compose.prod.yml`
passes it explicitly); `AINEWS_DAILY_SIGNALS_MAX_*` and `AINEWS_DAILY_SIGNALS_COMPARABLE_FROM` in the
server `.env` have no effect there. Set caps per run with `--max-calls`, `--max-seconds`, `--max-usd`.

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

# briefs for past days (007): extraction is cached, so the run total goes to briefs
$L $C -e AINEWS_DAILY_SIGNALS_ENABLED=true app ai-news daily-signals --report-date 2026-10-18 \
   --backfill-days 9 --max-usd 0.45
```

`ai-news daily-signals` options: `--report-date` (default yesterday UTC; completed days only),
`--backfill-days N` (1-800), `--max-calls`, `--max-seconds`, `--max-usd` (override the
`AINEWS_DAILY_SIGNALS_MAX_*` settings for this run), `--cache-dir` (default `data/daily-signals`),
`--recompute-only`, `--recompute-all`, `--retry-skipped`. It prints one JSON line and exits 0 for every
documented state (`ok`, `disabled`, `missing_provider_key`, `recompute_only`, `cap_reached`,
`deadline_reached`, `provider_unavailable`, `usage_exceeded_bound`); 1 means an unexpected error.
The line has a `brief` block (`null` without a paid run): `model`, `days` (per day `ok`, `invalid`,
`cached` or `skipped:<reason>`, e.g. `brief_budget_exhausted`, `brief_model_unpriced`, `cap_reached`,
`deadline_reached`, `packet_too_large`), `run` (`calls`, `usd`) and `terminal_reason`. A brief failure
never changes `state`, the extraction results or the snapshots. `reports_kept` counts stored days
left as they were (settled, or lost articles); `reports_lost_articles` lists the days whose
articles were pruned or deleted after their snapshot.

## Cost and limits

- The ledger prices every call as an upper bound (all input tokens at the cache-miss peak price
  $0.30/M, output $1.20/M): about $0.0004-0.0009 per article, $0.05-0.08 for a day of 60-90 articles.
  DeepSeek bills cache hits and off-peak hours lower; Phase 7 (1,610 calls) was $0.64 by the ledger,
  $0.26 at list prices and $0.14 billed. Budgets read against the ledger are therefore conservative.
- Per-run caps, checked before every provider call with a reservation: calls
  (`AINEWS_DAILY_SIGNALS_MAX_CALLS`, 200), USD (`AINEWS_DAILY_SIGNALS_MAX_USD`, 0.50) and an app-side
  deadline (`AINEWS_DAILY_SIGNALS_MAX_SECONDS`, 2700; no call starts with less than 95 s left).
  Three consecutive failed attempts stop the run.
- The ledger `data/daily-signals/ledger.sqlite3` (mode 0600) records every physical call; a saved 200
  answer is replayed instead of paid again. Each paid run writes
  `data/daily-signals/runs/<run_id>.json` (no key, no article text).
- Budgets across several invocations (validation, backfill) are tracked by the operator: pass the
  remaining budget as `--max-usd` and add up `run.usd` and `brief.run.usd` from the run reports.
- **Brief (007).** `--max-usd` (or `AINEWS_DAILY_SIGNALS_MAX_USD`) is the total for the run: briefs
  get what extraction left, at most $0.05 per target day; with nothing left every target is
  `skipped:brief_budget_exhausted`. Brief calls use the same ledger file (run id `<run_id>-brief`),
  priced per model (peak, all input as cache miss):

  | Model | Input $/M | Output $/M | Measured per day (2026-10-12..18) |
  | --- | --- | --- | --- |
  | `deepseek-v4-pro` (default) | 1.32 | 3.96 | $0.0027-0.0066, mean $0.0046 |
  | `deepseek-flash` | 0.30 | 1.20 | about $0.0012 (dry-run) |

  A model without a price entry is never called (`skipped:brief_model_unpriced`). Reservation per
  attempt is at most about $0.023 at the 12,000-byte input cap, so a day with one recovery stays under
  $0.05; about $0.15-0.20 a month with the default model.

## Fixing entities

All commands store an override, re-run reconciliation and recompute snapshots; no provider calls.
Settled days (older than two weeks) keep their snapshot; to apply an override to them, run
`daily-signals --recompute-only --recompute-all` afterwards.

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
- `daily_signal_briefs` (007) has no foreign key: links are stored as title, URL and publisher, so
  retention and the cleanup guard are unaffected.

## Deploy note (first deploy)

`deploy_prod.sh` starts the app before `alembic upgrade head`, and the app's `create_all()` can race the
migration (each create in `b6d1f0a7c3e5` is skipped when the table exists, but the two are not
serialized). If the deploy stops at the migration, rerun the whole deploy with the same target (same
image or tag) - not only `alembic upgrade head` - so the release receipt `.last_deploy_image`, the app
image and the timers are updated too.

007 adds `c3a8e5d27f14` (`daily_signal_briefs`) with the same skip-if-exists pattern; the same rerun
rule applies. After deploying 007 run `--recompute-only --recompute-all` once (methodology
`daily-signals-3`), then the brief backfill above if wanted.

## Rollback

Digest, articles and weekly data are never written by signals. Pick one level:

1. **Stop paid work**: set `AINEWS_DAILY_SIGNALS_ENABLED=false` in the server `.env`; the daily job
   reads it on its next run, and `docker compose -f docker-compose.prod.yml up -d app` applies it to
   the app. Code and tables stay; snapshots stay readable. This also stops new briefs; stored briefs
   stay visible.
2. **Revert code, keep the schema**: deploy a revert commit that removes the feature code but keeps
   `src/app/storage/migrations/versions/b6d1f0a7c3e5_add_daily_signals.py`. The six tables stay unused.
   To revert only 007, keep `c3a8e5d27f14_add_daily_signal_briefs.py` the same way; the
   `daily_signal_briefs` table stays unused and a recompute restores `daily-signals-2` snapshots.
   Deploying an older image instead does not work: its Alembic does not know `b6d1f0a7c3e5`, so the
   deploy stops at `alembic upgrade head`.
3. **Full rollback (drop the tables)**, in this order, while the feature image is still installed:

   ```bash
   sudo systemctl stop ai-news-daily-fetch.timer ai-news-daily-digest.timer
   flock -w 7200 /tmp/ai-news-auto-update.lock true      # wait for a running job
   docker compose -f docker-compose.prod.yml stop app     # else create_all() recreates the tables
   APP_IMAGE="$(cat .last_deploy_image)" \
     docker compose -f docker-compose.prod.yml run --rm app alembic downgrade a42b750d0c44
   APP_IMAGE=<previous release image> ./scripts/deploy_prod.sh   # or deploy-by-tag
   sudo systemctl start ai-news-daily-fetch.timer ai-news-daily-digest.timer
   ```

   The downgrade must run with the feature image (it holds the migration); the old release then finds
   the database at its own head.

## Not in the first release

Ledger budget ids, per-day spend caps, per-article attempt limits and `reset-attempts`, the watchdog
thread, the `split` override, stored duplicate candidates with `suspects`/`dismiss`. Each comes back
when its trigger in the plan ("Deferred (not in first release)") occurs.
