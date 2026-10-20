# Daily AI Signals

Feature 006 (`specs/006-daily-ai-signals/`), iteration 2 in 007
(`specs/007-daily-signals-brief/`: brief, one-liners, noise rules). The block at the top of `/` answers, for one
published digest day: what is new, which stories several publishers covered, what is spiking or rising,
what is cooling, and how many events of each type happened. Everything is computed from stored data;
page loads never call a provider.

Code map for maintainers (modules, tables, versions, where to change what):
`src/app/core/daily_signals.md`.

## How it works

1. **Scope.** Only articles of the published digest for day D count (digest items matched to articles
   by exact URL, then by canonical URL hash). Digests before `AINEWS_DAILY_SIGNALS_COMPARABLE_FROM`
   (2026-10-10) are history-only: they feed "first seen" but get no snapshot.
2. **Extraction.** One DeepSeek call per in-scope article (`daily-signals-extract-5`): named entities
   with type, vendor, role and an "is new" judgment with a source quote, the main event type and a
   novelty flag. Answers are validated against the article text (names and quotes must occur in it;
   a quote that dates the release before the article clears "new"). Results are cached per article,
   content hash and version.
   - **Input kinds** (stored as `input` in the extraction provenance): `full` - title and content when
     the content has at least 300 characters; `title_summary` - title and the stored RSS summary
     (HTML removed, at most 1,500 characters) when the content is shorter; `title_only` - neither.
     Legacy history (before 2026-10-10) is much thinner than recent days: on production about 443 of
     1,642 matched history items have full text and about 1,009 more have a summary. A title-only
     article usually yields no entities but still counts as processed for day coverage (coverage
     measures the pipeline, not how rich the source is).
3. **Evidence and identity.** Every mention is stored as evidence that survives article retention.
   Entities are derived from all evidence by a deterministic reconciliation (normalized keys, vendor
   classes backed by company mentions, packaging families) plus operator overrides.
4. **Snapshots.** At the end of each run, every comparable published day of the last 400 days is
   recomputed in memory and stored when its payload changed.
5. **Brief (007).** After the snapshots, a paid run writes a short "In brief" for each target day: one
   call to `AINEWS_DAILY_SIGNALS_BRIEF_MODEL` (default `deepseek-v4-pro`, prompt
   `daily-signals-brief-3`) with the stored snapshot of D and the digest summaries of the referenced
   articles (at most 12,000 bytes; on a quiet day every digest item, max 30). The answer is checked
   mechanically: known article ids, an exact 5-40 word quote from a cited article, numbers and
   capitalized names present in the cited text, at most one sentence per story, 3-5 sentences (1-2
   on a quiet day). An invalid answer gets one recovery attempt, then the day is stored `invalid` and
   shows no brief. Briefs live in `daily_signal_briefs` (one row per day) keyed by an input hash of
   packet, prompt version and model: an unchanged input is never paid twice, a changed snapshot is
   regenerated on the next paid run, page loads never generate. Target days: the run's days with a
   usable snapshot, plus D-1 in a one-day run when D-1 has no current `ok` brief. The check is
   syntactic: it catches invented names, numbers and quotes, not a wrong verb.

## What the reader sees (owner decisions OD1-OD7)

- **In brief** (007): the generated sentences, each with numbered source links, an italic style and the
  muted note "Written by AI from the linked articles; check the sources." A missing or invalid brief
  shows nothing. A **quiet day** (fewer than 20 digest items or no multi-publisher story) opens with
  an app-written line, e.g. "Quiet day: 14 items, no story covered by more than one outlet.", and
  shows the brief, the chips and only the cards that have items (no empty-state cards).
- **New**: an entity first seen in our corpus on D that an article of D presents as newly announced
  (model judgment). Confirmed = at least 2 publishers, shown first with "N outlets"; single-source
  items follow muted with "via <publisher>" (no badge). Each item has one line saying what it is
  (007, no provider call): the first digest-summary sentence of its linked articles that names it and
  has a launch or "is a" verb; a naming sentence when the novelty quote has fewer than 8 words; else
  the novelty quote, shown in quotation marks; at most 140 characters. `variant of X` is shown only
  for a specific earlier entity of the same type (a digit or several tokens after removing the vendor;
  never a family word such as GPT, Claude, Gemini, Llama, Muse, Grok, Qwen, Clef, Nemotron). Packaging variants of a known model (sizes, quantization, instruct/base) are not New;
  a new named version or a GA release after a preview is. People and "other" are never New. Two
  deterministic safety nets: the name must look like a name (an uppercase letter or digit, or one
  hyphen/dot-joined token, so "dynamic workflows" is not New), and a name that already occurs in an
  earlier published digest item (title or summary) is not New, even when that article's extraction
  found nothing. A digest text that frames the name as not yet released (`preview`, `beta`, `alpha`,
  `waitlist`, `early access`, `roadmap`, `plans to`, `will release`, `will launch`, `coming soon`,
  `upcoming`, also in parentheses) does not count, so a GA release after a preview stays New. A
  single common-word name ("Beam") is refused this way only when its vendor's name appears in the
  same digest item; without a known vendor it is never refused lexically. Refused items are kept in the
  stored snapshot as `new_suppressed` (reason, matching day, matched words and a text snippet; not
  part of the API response). The list
  shows 8 items: confirmed first, then early models, hardware, benchmarks, datasets, techniques,
  companies, products, policies. "History: N complete days." is shown while fewer than 30 complete
  days precede D.
- **Top stories**: clusters of articles about the same event with at least 2 publishers (max 5).
- **Spikes / Rising**: Rising compares the last 7 days with the previous 7 against a volume-adjusted
  expectation; it needs two windows with at least 6 complete days each (earliest D = 2026-10-23).
  Until then the card shows **Spikes**: D's count against the mean of at least 3 complete trailing days
  with at least 10 digest items. 007 folds a spike into the item it duplicates: a top story holding at
  least half of its articles that names it (entity, label, or for a company the vendor of a story
  entity), else a New item or an earlier spike of that company; the target shows "spike: <names>".
  A company spike with no story holding 2 of its articles is dropped as diffuse. Kept spikes show a
  reason (the label of D's story with most of their articles), e.g. "today 6 vs 1.3/day - <label>".
  Folded and dropped spikes are recorded in the stored snapshot as `spikes_folded`. When nothing is
  left the Spikes card is hidden and its note moves to the status line.
- **Cooling**: only when the windows are usable; collapsed by default.
- **Event chips**: stories per "hard" event type (releases, launches, funding, acquisitions,
  partnerships, infrastructure deals, hardware, regulation & policy, legal, security incidents, people
  moves); the rest fold into "+N more" with the list as a tooltip (display only).
- Entities with conflicting vendors (`needs_review`) are excluded from New, Rising and spikes.

Thresholds are code constants (`Thresholds` in `src/app/core/daily_signals_compute.py`), recorded in
every snapshot; a change is a code release with a `METHODOLOGY_VERSION` bump (007: `daily-signals-3`;
recompute with `--recompute-only --recompute-all` after deploying it).

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
never changes `state`, the extraction results or the snapshots.

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
