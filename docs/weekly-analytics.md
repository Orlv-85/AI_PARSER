# Weekly Attention Analytics v2

Both deploy workflows enforce `AINEWS_WEEKLY_V2_ENABLED=false`, and production
Compose defaults it to false. Deployments remove the managed weekly cron with
`AINEWS_WEEKLY_CRON_ENABLED=0`; the deploy script also defaults it to zero.
Repository variables cannot silently re-enable weekly during these deployments.
Local application settings still default to false. Any future reactivation must
explicitly change both the runtime flag and scheduling policy. It does not launch
a backfill. Runtime quality gates still suppress
confirmed labels when comparable coverage or classification is insufficient. Its arithmetic measures
publisher-balanced news attention, using complete observations rather than ranking.
The API keeps its existing fields and adds metrics, evidence, quality reasons and
immutable snapshot revisions. Manual/external reports remain `legacy`; a legacy POST
cannot overwrite a published v2 revision. GET only reads existing v2 snapshots and
never calls a model. Daily digest generation and ingestion ranking are unchanged.

Run additive migrations before collecting coverage with this version:

```bash
./venv1/bin/alembic upgrade head
```

Collection records publication provenance and scheduled source outcomes even with
v2 publication disabled and `AINEWS_FETCH_EMIT_SOURCE_METRICS=false`. Coverage requires
90% successful scheduled slots and six successful days per week. Empty feeds and
304 are successes; malformed feeds, unknown publication dates, incomplete HTML
collection and known truncation cannot prove healthy coverage. RSS observations are
preserved from the entire downloaded feed even when legacy ingestion stops early.
HTML publication metadata is recorded separately, without changing ingestion dates.
Existing article/alias discovery timestamps never establish verified history.

Publisher ownership overrides use `AINEWS_WEEKLY_PUBLISHER_OVERRIDES`, a JSON object
mapping domains to group IDs, for example `{"example.com":"owner","other.com":"owner"}`.
The fallback groups common registrable domains conservatively; review ownership and
unusual/public suffixes before release. Changes to grouping/configuration reset
comparability rather than silently rewriting historical coverage.

After establishing coverage and reviewing the taxonomy, run the v2 worker against
the same database as ingestion. The following invocation authorizes provider work
within the explicit per-run budgets shown; configure `JEV_API_KEY` and `DS_API_KEY`:

```bash
AINEWS_WEEKLY_V2_ENABLED=true \
AINEWS_WEEKLY_JEV_DECISION_BUDGET=1000 \
AINEWS_WEEKLY_AMBIGUITY_BUDGET=100 \
AINEWS_WEEKLY_NARRATIVE_BUDGET=16 \
./venv1/bin/ai-news weekly-analytics --report-date 2026-10-04 --limit 200
```

`--limit` is retained as a compatibility hint; it never limits counting. The input
safety cap is explicit (`AINEWS_WEEKLY_INPUT_SAFETY_CAP`, default 100000): hitting it
suppresses confirmed labels. Jobs freeze publication observations, cutoff, coverage,
taxonomy, thresholds and provider configuration. A unique input key and date-wide
publication lock prevent duplicate work and competing revisions. Expired leases
can resume; cached decisions persist across runs. `--enqueue-only` records work;
`--drain-only --max-jobs 8` processes pending/retry work. Provider budgets and the
900-second wall limit apply across the drain invocation, including retries.

Weekly model/prompt settings are `AINEWS_WEEKLY_JEV_MODEL`,
`AINEWS_WEEKLY_DEEPSEEK_MODEL` and `AINEWS_WEEKLY_PROMPT_VERSION`. Jev uses the existing
timeout setting. DeepSeek timeout defaults to 60 seconds; at most two transient
retries honor Retry-After. Input is conservatively bounded by prompt character count
against `AINEWS_WEEKLY_INPUT_TOKEN_CAP` (16000); DeepSeek output is capped by
`AINEWS_WEEKLY_OUTPUT_TOKEN_CAP` (1200). Calls/tokens/failures are recorded without keys.
Narrative failures retain metric-derived text and stored citations.

The existing `scripts/run_weekly_analytics_job.sh` detects the flag inside the app
container and drains this service, preserving cron cadence. Monday ingestion only
enqueues v2 work. Direct `digest_generator.py publish-feed-weekly` remains a legacy
adapter unless the host explicitly sets `AINEWS_WEEKLY_V2_ENABLED=true`; in that mode
it uses the local configured DB and the shared worker (its base-url stays accepted).

Export an eight-week comparison and deterministic manual review samples, without
provider calls:

```bash
./venv1/bin/ai-news weekly-analytics-audit --report-date 2026-10-04 \
  --weeks 8 --output tmp/weekly-review.json
```

The export includes section counts, rejected candidates/quality reasons, evidence,
up to 200 stratified assignments and 50 event pairs, and worker usage. It deliberately
does not certify precision without manual labels. Review multilingual, ambiguous
and unseen-topic examples, trace every displayed trend, and audit missed signals.
Separate tuning and evaluation weeks; freeze revised thresholds under a new
methodology version. Require the release criteria in
[trend-spec.md](../specs/010-weekly-ai-analytics-for-management-dashboard/trend-spec.md).
If historical coverage is unavailable, collect two completed weeks for Up/Down and
35 observed days for New. Complete the replay and semantic review to assess trend
quality; enabling the runtime flag does not certify historical coverage or precision.

Explicit backfill creates new revisions; original legacy reports remain stored.
A failed or insufficient regeneration keeps the last ready revision. Rollback sets
the v2 flag to false while retaining evidence and snapshots; no destructive migration
is required. Unverified legacy publication cannot replace a date with a v2 snapshot.
