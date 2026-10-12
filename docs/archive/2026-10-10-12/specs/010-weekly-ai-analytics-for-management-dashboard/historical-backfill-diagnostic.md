> **ARCHIVE — historical record, 2026-10-10–12.** Saved prompts, approvals, commands and runtime states are superseded; do not use this file to resume work. See the [archive index](../../README.md) for completed outcomes and remaining work.

# Historical backfill diagnosis and isolated preview

Read-only production inspection: 2026-10-10, PostgreSQL transaction at
14:36:13 UTC, `REPEATABLE READ / READ ONLY`. No providers, enqueue, fetch or
production configuration changes were used during diagnosis.

## Runtime and available evidence

- Host checkout: `v0.1.74`, commit `6d6f512238a127e769770f77f2ca333ddb82e132`.
- Running image: `ghcr.io/orlv-85/ai-parser:v0.1.74`, image ID
  `sha256:153fcfe6e782dd57b90a2b3b7a7041a60f14761d0b3b1f6329343a668e695e7f`.
- Effective `AINEWS_WEEKLY_V2_ENABLED=false`. Weekly models: `jev-1.13.0`
  and `deepseek-flash`; prompt `weekly-1`; both provider keys present.
- Running `weekly_worker.py` and `pipeline.py` hashes match the local released
  files. No deployment tracking or rollout was requested or performed.
- 8,337 articles, 164 registered sources, 46 legacy weekly reports, zero aliases.
  Article publication timestamps range from July 2 through October 10, 2026.
- `weekly_input_observations`, `weekly_coverage_attempts`,
  `weekly_source_versions`, `weekly_decisions`, `weekly_topic_versions`,
  `weekly_jobs`, `weekly_snapshots` and `weekly_publications` all contain zero
  rows. `fetch_runs` also contains zero rows.

## Exact UTC windows and volumes

All ends below are exclusive midnight UTC. W0 is the current seven days; W1
is the previous seven days. H is the preceding 28 days and includes W1.

| Report | W0 start/end | W0 articles / sources | W1 articles | H start/end | H articles | Full 35-day input | Clean input characters |
|---|---|---:|---:|---|---:|---:|---:|
| 2026-09-06 | 08-31 / 09-07 | 597 / 50 | 563 | 08-03 / 08-31 | 2238 | 2835 | 8065971 |
| 2026-09-13 | 09-07 / 09-14 | 625 / 51 | 597 | 08-10 / 09-07 | 2301 | 2926 | 9333470 |
| 2026-09-20 | 09-14 / 09-21 | 450 / 46 | 625 | 08-17 / 09-14 | 2353 | 2803 | 9257279 |
| 2026-09-27 | 09-21 / 09-28 | 107 / 22 | 450 | 08-24 / 09-21 | 2235 | 2342 | 7253275 |
| 2026-10-04 | 09-28 / 10-05 | 1021 / 72 | 107 | 08-31 / 09-28 | 1779 | 2800 | 9947544 |

The five W0 windows contain 2,800 articles. The union of all historical inputs
is `[2026-08-03, 2026-10-05)`: nine weeks, 5,038 unique articles, 91 sources,
90 fallback publisher groups and 16,057,909 cleaned characters. Those publisher
groups are domain fallbacks, not audited ownership. Five separate inputs contain
13,706 rows before shared caching. Median article text is 272 characters; 76
articles have only a title, 3,466 have summaries and 1,496 have content.

The corpus has publication timestamps on 60 of the 63 days. September 20, 26
and 27 have no stored article publications. This does not establish failed or
healthy collection on those dates. September 21-27 has only 107 articles and
no full content; September 28-October 4 has 1,021 and 716 with content. These
input changes must not be interpreted as confirmed changes in topic attention.

Detailed source IDs/counts, publication minima/maxima, text volumes and original
legacy payloads are in the local diagnostic export
`tmp/weekly-backfill-diagnostic-2026-10-10.json`.

## Historical coverage assessment

Contrary to the earlier local-only inventory, the host has a retained structured
log at `/var/log/ai-news-auto-update.log`. Its per-source entries span March 15
through October 9. The requested 63-day period has dated source outcomes every
day; including two October 4 recovery logs there are 6,694 unique run/source
entries, of which 1,866 flag an early stop.

This is useful evidence of actual collection activity. It does not provide frozen
configuration/ownership versions, a complete expected-attempt ledger or uniformly
proven parser/retrieval completeness. Current configured intervals range from
30 minutes to seven days, while the current host auto-update cron is daily; current
values cannot establish historical expected slots. Sources and grouping definitions
cannot be reconstructed from the absence of articles or the latest source state.
Early-stop entries also cannot certify complete input. No historical cohort meeting
the unchanged v2 coverage gates was established; historical coverage remains unknown.

## Why the ordinary v2 worker is unsuitable

Every one of the 5,038 frozen inputs has `publication_provenance=legacy_unverified`.
`weekly_worker._classify` performs enrichment and then forces these observations
to `eligible=False`. Therefore an ordinary paid run can classify the corpus while
counting none of it, with empty confirmed sections. Even independently recovered
coverage would not repair publication provenance automatically. Historical health
and publication provenance must not be invented to make this run succeed.

Existing legacy sections (New / Up / Down) are respectively 3/0/3, 3/0/3,
10/0/10, 10/0/10 and 10/1/10 for the five dates. These are stored legacy cards,
not verified topic/event measurements.

## Preview preparation and authorization

Separate branch: `feat/weekly-historical-preview`.
Runner: `scripts/weekly_historical_preview.py`. No verified v2 calculator,
worker, ingestion behavior, feature flag, legacy writer or quality gate is changed.

The runner uses frozen exports and an isolated SQLite database for durable
date jobs, progress, semantic decision caching and an HTTP-attempt budget ledger.
It reuses JEV assignment/event checks and evidence-validated DeepSeek narratives.
It freezes the taxonomy and does not create new topics. Accepted semantic labels
are useful inside the preview, while original publication provenance is retained.
Unresolved/non-AI articles and ambiguous event grouping remain inspectable.

Output status is `historical_preview`, with unconfirmed coverage and unverified
dates. The user-facing notice is: **historical data, coverage is not confirmed**
(Russian: "исторические данные, покрытие не подтверждено"). Confirmed
`new`, `trending_up` and `trending_down` arrays remain empty. Preview counts
describe stored articles, observed publisher groups and semantic event groups;
they are not comparable-cohort shares or confirmed trends. Every completed output
uses a separate numbered JSON artifact. Original reports are copied into the
frozen manifest and never overwritten or published by this runner.

The user subsequently selected a pilot for **2026-10-04 only**, comparing W0
with W1: `[2026-09-21, 2026-10-05)`, 1,128 articles, 1,085 distinct bounded
clean texts, including 28 title-only articles. Earlier historical inputs remain
preserved in the export but are not enriched for this pilot. The other four
reports have not been authorized for paid execution yet.

Explicit user approval: **$2 total**, including both providers, retries and
resumed worker invocations. Initial pilot estimate was $0.50-2; actual usage must
be reported after execution. Per-run 1,000 JEV / 100 ambiguity / 16 narrative
limits remain in addition to the durable total dollar limit. Each HTTP attempt
reserves its capped maximum cost before transmission; unknown or failed usage
keeps that reservation. Successful usage is reconciled against provider token
counts. Calls and tokens remain separated by provider across resumptions.

Prices checked against official documentation on 2026-10-10:

- [TypeSafe models](https://docs.typesafe.ai/models): JEV $0.042 per million
  input tokens, output free.
- [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/): Flash
  peak cache-miss input $0.30 / output $1.20 per million tokens; off-peak
  $0.15 / $0.60. Cache-hit input $0.006 peak / $0.003 off-peak. Reservations use
  peak cache-miss prices; reconciliation uses request time and cache-hit usage.
  Any provider billing adjustments require verification against its account ledger.

Server pilot artifacts:
`/opt/ai-news/data/weekly-history/pilot-20261004-budget2/`.
The runner executes in the existing released container against these separate
artifacts. It never writes the production PostgreSQL database or publishes a
replacement report. Application settings and scheduling are unchanged.

## Validation

- New mock tests cover provider-free preparation, immutable frozen input,
  preservation of original history/legacy reports, budget persistence across
  process restarts, pre-request retry accounting, assignment cache reuse and
  preview-only output after resumption.
- Scoped tests passed: historical preview, weekly worker, trend calculator,
  enrichment and storage test modules.
- Ruff passed on the new script and its tests; script compilation passed.
- Initial expanded test invocation was affected by a temporary auth environment
  override; rerunning with explicit empty test auth values passed. No local or
  production auth configuration was edited.
- No commit/push performed; full repo-wide lint/pytest were not run for this
  isolated preview script. No live semantic precision certification is claimed.

## Pilot outcome

Completed revision 1 on the server at 2026-10-10T15:17:37 UTC, approximately
25 minutes after the first model request. All 1,128 pilot inputs were processed.
290 received a topic, 271 remained unresolved and 567 were rejected as non-AI.
There are 23 observed topics. The leading current-week article counts are coding
agents 67, language models 37, enterprise agents 22, inference infrastructure 19,
AI security 17 and agent tooling 16. Their previous-week counts are 0, 4, 4, 7,
2 and 1 respectively. These are corpus observations, never confirmed directions
or novelty. Some input URLs are product/about pages rather than dated news.

2,399 semantic event comparisons produced no accepted semantic merge. Exact
URL/content grouping still collapsed some copies. 245 ambiguous pairs and 110
candidate-limit cases remain recorded; event grouping is explicitly incomplete.
Eight DeepSeek narrative attempts all fell back to templates: six responses did
not make explanation equal the concatenated validated claims, and three exceeded
the six-claim cap (these reasons overlap). Other validation/support failures may
also apply. Their original cached JSON remains available for inspection. The
preview therefore provides topics, counts and sourced excerpts, with template
prose; quality gates were not lowered to accept the model's wording.

Total recorded attempts: JEV 3,844; DeepSeek ambiguity 332 and narrative 8.
JEV usage: 4,954,854 input / 347,748 output tokens (output uncharged).
DeepSeek usage: 521,601 input / 46,818 output tokens, no input cache hits.
Token-price calculation is approximately $0.2081 JEV + $0.1063 DeepSeek =
$0.3144; the conservative ledger rounds each HTTP cost up to a microdollar,
recording **$0.316503 total** against the approved $2 maximum. There are zero
unknown-usage attempts remaining. These are usage-derived costs, not a retrieved
provider account invoice.

Server immutable artifacts include `2026-10-04.r1.json`, a Russian-warning
`2026-10-04.r1.html`, the frozen manifest/original report, shared decisions,
durable jobs/progress and invocation logs. Local review copies are in `tmp/`.
Production PostgreSQL weekly jobs/snapshots/publications/decisions remain empty;
the original 2026-10-04 legacy report matches its saved pre-run payload exactly.
The other four dates were not processed with paid providers.

An independent runtime change occurred during this session: the final read-only
inspection observed `v0.1.75` and `weekly_v2_enabled=true`, versus `v0.1.74` and
false initially. This pilot did not deploy or change that setting. As of the final
inspection, the current October 5-11 UTC week has 821 articles from 54 sources,
but weekly input observations, source versions and coverage attempts are still
empty. More current articles alone cannot establish trustworthy weekly coverage.
The isolated preview cache is not the production worker cache, and the pilot's
$2 limit is not a budget cap on scheduled production jobs.
