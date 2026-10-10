# Weekly AI Analytics v2: evidence-based trends with JEV and DeepSeek

Date: 2026-10-10
Status: Proposed; specification only, implementation not started.
Parent: [Weekly analytics specification](spec.md).
Delivery: [Implementation plan](trend-plan.md).

## 1. Problem and observed implementation

The UI can show an empty Trending Up section while Trending Down contains items.
The current implementation has structural reasons for this imbalance:

- `WeeklyAnalyticsRepo._generate_report()` selects only five highest-ranked
  articles per week through the default `_list_articles(limit=5)`.
- `_build_section_rows()` matches short English title token sets. An unmatched
  current title becomes New; an unmatched previous title becomes Trending Down.
- Trending Up requires a matched title and an increase in one representative
  article's `rank_score`. A matched topic with a lower score is not classified Down.
- `rank_score` includes freshness, relevance, source weight, and alias bonus;
  it is not a measurement of weekly topic attention.
- `scripts/digest_generator.py::build_feed_weekly_payload()` independently repeats
  this rule. `run_weekly_analytics_job.sh` invokes this feed-based publisher.
- Stored reports are returned before generation. Fixing generation alone does not
  repair previously saved empty sections.
- The original feature packet describes Antigravity, but the current repository
  generator returns its local fallback directly. This proposal supersedes the
  original provider and section-derivation requirements for v2 only.

These are code findings, not a verified diagnosis of a particular production
report. Before rollout, inspect the affected report date, saved payload, publisher,
and actual input coverage.

## 2. Product contract

The product measures **news attention within the monitored corpus**. It must not
equate coverage with market adoption, revenue, technological quality, or sentiment.

| Section | Meaning |
|---|---|
| Trending Up | An established topic gained a material share of comparable coverage. |
| Trending Down | An established topic lost a material share of comparable coverage. |
| New | A confirmed topic first observed in the current week after 28 observed days without it. |

New means new to this monitored corpus and lookback, not a world-first invention.
A renamed headline, newly added feed, or new article about an established topic
does not establish novelty. A new model release can be a driver of an established
topic; v2 does not automatically make every release a New topic.

Each topic has exactly one state per report: `new`, `up`, `down`, `stable`,
`resurfacing`, or `insufficient_evidence`. Only the first three fill the main cards.
Stable topics and unconfirmed signals remain inspectable in an expandable view.
There is no minimum quota of cards. Empty sections must explain their reason.

## 3. Responsibilities

| Component | Responsibility | Forbidden responsibility |
|---|---|---|
| JEV | Article relevance, assignment to a stable topic, bounded same-event checks, support checks for narrative claims | Decide weekly direction from intuition or generate prose |
| Python trend engine | Deduplication, coverage gates, arithmetic, section membership, sorting, evidence selection | Infer missing observations as zero |
| DeepSeek | Resolve ambiguous semantic assignments, propose emerging topic definitions, explain computed changes using supplied evidence | Change metrics, direction, thresholds, invent URLs or require every section to be nonempty |

JEV supports typed Choice/Noul decisions; DeepSeek supports JSON output. These
capabilities justify this division, but neither typed output nor JSON guarantees
factual correctness. Provider scores are semantic confidence, not a statistical
probability that a market trend is real.

## 4. Time and complete input

FR-01. For report date D, in UTC:

- Current W0: `[D-6 at 00:00, D+1 at 00:00)`.
- Previous W1: `[D-13 at 00:00, D-6 at 00:00)`.
- Novelty history H: `[D-34 at 00:00, D-6 at 00:00)`, exactly 28 days.
- Select by article publication time. Persist the generation cutoff and included
  observation IDs. Later discoveries require a new explicit report revision.
- A date whose current week is not yet complete produces a provisional report;
  it cannot carry confirmed Up/Down/New labels.

FR-02. Read all eligible observations, with deterministic pagination if needed.
Never calculate metrics from the ranked top 5, top 200, digest, or LLM excerpts.
Existing CLI `--limit` must remain accepted, but in v2 it may bound page size or
evidence presentation only. A retrieval safety cap produces `input_incomplete`,
not a silently truncated confirmed report.

FR-03. Preserve all input and excluded counts. Invalid dates and unavailable text
remain visible as quality counters. `rank_score` may break evidence-display ties;
it cannot decide topic membership, counts, or trend direction.

## 5. Stable semantic identity

FR-04. Introduce a versioned topic registry separate from the existing seven
digest categories. Begin with approximately 20-40 reviewed topics, including
coding agents, enterprise agents, inference infrastructure, open-weight models,
multimodal models, AI regulation, and AI security.

Each topic has an immutable ID, display label, definition, exclusions, aliases,
parent category, and taxonomy version. Company names alone are not topics.
Each article receives one primary topic or `unresolved`; secondary descriptive
tags do not contribute additional counting weight.

FR-05. Weekly enrichment is separate from ingestion scoring. Reuse existing JEV
relevance/category values only when provenance and versions are compatible;
current stored relevance alone does not prove it came from JEV.

1. JEV evaluates AI relevance and a Choice over the frozen topic definitions plus
   `other` and `insufficient_information` using title, summary, and available text.
2. Proposed starting gates: relevance >= 0.70 and topic confidence >= 0.80.
3. Below the gates, DeepSeek returns a constrained JSON assignment with article ID,
   candidate topic ID, supporting text span, and ambiguity reason. Acceptance
   requires a real source span and JEV support >= 0.85; otherwise leave unresolved.
4. DeepSeek may group unresolved materials into a candidate topic definition.
   Require at least three distinct events across three publisher groups, then JEV
   must support the assignments at >= 0.85. Reject a candidate that only renames or
   subdivides an existing topic without an approved taxonomy change.
5. Freeze any accepted taxonomy revision and re-evaluate the entire 35-day input
   snapshot with it before computing New. Do not assign a newly created topic
   only to W0 and interpret its absent historical assignments as novelty.

Entity aliases and topic definitions must support multilingual headlines.
Keep the unknown cases; never force every document into a topic. Cache by cleaned
text hash, task, provider/model, prompt version, and taxonomy version. Persist
accepted outputs: replay reproducibility must not depend on fresh model calls.

## 6. Counting and source comparability

FR-06. Distinguish an article, an event, a publisher group, and a topic:

- Canonical URLs, content hashes, and known aliases remove exact duplicates.
- A semantic event is one specific announcement or occurrence. Candidate lookup
  uses normalized entities, publication time, and text similarity; JEV confirms
  same-event matches at >= 0.90. Do not merge independent releases just because
  both mention the same company. Persist ambiguous pairs for inspection.
- Publisher groups collapse multiple feeds/domains owned by the same publisher.
  Store explicit grouping overrides; a registrable domain is only a fallback.
- At most one observation per `(event_id, publisher_group_id, week)` contributes.
  Republishing the same event 20 times by the same publisher adds no weight.
- Cross-publisher syndication contributes at most one observation per publisher
  but remains one global event, so a single widely copied launch cannot satisfy
  the multi-event gate by itself. Publisher diversity does not prove independent
  original reporting; label this metric "publisher groups".
- Preserve publication dates for individual alias observations. Existing aliases
  with discovery timestamps alone cannot prove historical publication coverage.

FR-07. Build a comparable publisher cohort C, independent of the topic:

- Candidate groups must be configured before W1 starts; newly added groups are
  excluded from both sides of that comparison.
- A group is healthy in a week when at least 90% of its scheduled collection
  attempts succeeded and it had successful collection on at least six days.
  HTTP 304 counts as successful coverage; zero new items does not mean failure.
  Sources scheduled less than daily are excluded from this initial methodology.
- Require healthy status in both weeks, at least five eligible publisher groups,
  and retention of at least 80% of the groups healthy in W1. A failed publisher
  is excluded from both weeks, never represented as a current-week topic zero.
- The coverage ledger must distinguish parser/network failure, valid empty/304,
  and known retrieval truncation. Known truncation disqualifies affected coverage.
- For per-publisher proportions, require at least one eligible AI event-observation
  in each week. A healthy publisher with zero eligible AI news cannot supply a
  denominator; exclude it from both sides and apply the retention gate again.
- Require >= 100 eligible event-publisher observations per week in C, resolved
  topic assignment for >= 90% of those observations in each week, and no more than
  five percentage points difference in assignment completeness between weeks.
- Keep unresolved AI observations in denominators and expose their share.

These are proposed conservative quality gates, not established industry constants.
Tune on historical fixtures, version the values, and freeze them before evaluation.
Never lower a threshold at runtime simply to fill Trending Up.

FR-08. Coverage history must be persisted per source/day with expected and completed
attempts, outcomes, configuration version, and completeness. Current aggregate
`FetchRun` records and latest `Source.last_checked_at` are insufficient to prove
historical per-source coverage. Structured per-source logs may backfill the ledger
only if complete and timestamped. Otherwise historical coverage is `unknown`.

## 7. Deterministic metrics and rules

FR-09. For topic t, publisher s in C, and week w:

```text
n[t,s,w] = number of distinct eligible events assigned to t for s in w
n[s,w]   = number of all eligible AI events for s in w, including unresolved
P[t,w]   = mean over s in C of n[t,s,w] / n[s,w]
delta_pp = 100 * (P[t,W0] - P[t,W1])
growth   = (P[t,W0] - P[t,W1]) / P[t,W1]  # only when P[t,W1] > 0
E[t,w]   = distinct global events for topic t in w
S[t,w]   = publisher groups covering topic t in w
days[t,w] = UTC publication days with topic observations in w
```

Equal publisher weighting prevents a prolific publisher from automatically
dominating the corpus. Display raw event and publisher counts beside normalized
share. Growth is a change in share, not a change in raw article volume.

Define `supported(t,w)` as E >= 5, S >= 3, and days >= 2.
Use full precision for rules; round only display values.

FR-10. Apply quality gates first, then classify:

| State | Proposed v2 rule |
|---|---|
| New | supported(t,W0), no accepted observations in H, and complete novelty coverage below |
| Resurfacing | supported(t,W0), P[t,W1] = 0, and at least one accepted observation in H |
| Up | P[t,W1] > 0, supported(t,W0), growth >= 0.30, delta_pp >= 1.0, E[t,W0] - E[t,W1] >= 3 |
| Down | P[t,W1] > 0, supported(t,W1), growth <= -0.30, delta_pp <= -1.0, E[t,W1] - E[t,W0] >= 3 |
| Stable | Comparable data, known baseline, no material-change rule satisfied |
| Insufficient evidence | Failed quality gates, ambiguous novelty, or unsupported zero-baseline signal |

W0 count zero can be Down only if current coverage is healthy and the Down rule
passes. W1 zero never yields an infinite growth value: `growth_pct` is null.
Small movements remain visible as stable; an increase from one event to two is
not a confirmed trend. An increase in negative coverage is still Up in attention.

FR-11. New additionally requires a cohort healthy in all four historical weeks
and W0, with the same volume/assignment gates and at least 80% of C retained.
Recompute current support on that novelty cohort and inspect H across all stored
sources: a positive historical match anywhere disqualifies New. Absence only has
meaning inside the observed cohort. Plausible unresolved historical matches
prevent confirmation. Missing historical coverage yields `insufficient_history`,
not New; Up/Down can still work with a valid two-week baseline.

FR-12. Sort Up/Down by absolute delta_pp, then event count on the supported side,
then topic ID. Sort New by current normalized share, then events and topic ID.
Show up to five cards per section initially; retain every computed candidate in
the snapshot. New and resurfacing cannot also appear as Up.

## 8. DeepSeek explanation and evidence

FR-13. After metrics are frozen, send DeepSeek a bounded evidence packet per selected
topic: topic definition, dates, exact metrics, quality flags, and up to six source
excerpts from distinct events and publisher groups. Include previous-week evidence
for Down and both-week context for Up. Evidence sampling never changes counting.

Output JSON contains topic ID, a short explanation, explicit claim-to-evidence-ID
references, and an optional management implication identified as interpretation.
DeepSeek cannot return authoritative section names, metric values, or arbitrary URLs.
The application assembles those from the immutable snapshot and source records.

FR-14. Validate JSON schema, completion status, topic/evidence IDs, quoted spans,
numeric mentions, and consistency with the computed direction. JEV checks each
factual claim against its cited excerpts; require >= 0.85 support. This check is a
quality filter, not proof of truth. Reject unsupported causal explanations such
as "demand fell" when only lower coverage is observed.

On invalid output, provider timeout, empty content, or failed support check, use
local text built from the same metrics and citations. A DeepSeek outage changes
narrative quality, not confirmed section membership. A JEV outage with incomplete
cached enrichment instead reduces data quality and can suppress confirmation.
Treat source text as untrusted data in both prompts.

## 9. UI and backward-compatible API

FR-15. Preserve `report_date`, `date_from`, `date_to`, `summary`, `new`,
`trending_up`, `trending_down`, and item `title`, `summary`, `url`.
Add optional fields through a weekly-specific item model, preserving digest types:

- Topic: `topic_id`, `state`, `event_count_current/previous`,
  `publisher_count_current/previous`, `share_current/previous`, `delta_pp`,
  nullable `growth_pct`, `first_observed_at`, `evidence[]`.
- Report: `methodology_version`, `taxonomy_version`, `snapshot_id`, `revision`,
  `generated_at`, `data_cutoff`, `status`, `narrative_mode`, `quality`,
  `section_status`, and `other_signals`.
- Evidence: stored article/event ID, title, HTTP(S) URL, publisher, publication
  date, window, and excerpt. Down may legitimately link to previous-week evidence.
- Status: `ready`, `provisional`, `insufficient_data`, or `legacy`.
- Narrative mode: `deepseek`, `template`, or `mixed`.

Do not accept client-supplied verified metrics without recomputing them. Preserve
the existing POST request shape for external/manual reports, mark those `legacy`,
and prevent old publishers from overwriting a v2 report with unverified content.
GET must not call providers or initiate paid enrichment. Missing v2 snapshots
return compatible arrays and an explicit availability reason.

FR-16. Each card shows topic, direction, share before/after, percentage-point
change, event counts, publisher counts, explanation, and expandable sources.
Example, using illustrative equal-volume publishers:

```text
Coding agents                         Trending Up
Share of coverage: 5.0% -> 12.0%      +7.0 pp / +140%
Distinct events: 5 -> 12             Publisher groups: 3 -> 5
Evidence: [current and prior sources]
```

Show report dates, compared dates, cohort size, data quality, generation time,
and a short methodology link. Make clear that share is publisher-balanced.
Do not render model confidence as "95% certain trend".

Replace generic "No items yet" in BOTH `weekly_analytics.html` and the
`digest.html` preview with one of:

- "No topics met the growth threshold this week."
- "No topics met the decline threshold this week."
- "No confirmed new topics in the observed 28-day history."
- "Insufficient comparable source coverage."
- "Collecting history to verify new topics."
- "Topic classification is incomplete."
- "This week is still in progress."

Keep exact machine-readable reasons including `no_qualifying_topics`,
`insufficient_history`, `coverage_unknown`, `source_outage`, `low_volume`,
`classification_incomplete`, `input_incomplete`, and `partial_window`.

## 10. Persistence and publication

FR-17. Store versioned topic assignments, event clusters and observations,
publisher grouping, source/day coverage, all topic metrics, evidence IDs,
classification outputs, threshold configuration, and an input fingerprint.
Use additive migrations compatible with SQLite and PostgreSQL. Preserve existing
reports and text fields; do not relabel historical legacy reports as verified v2.

FR-18. All weekly entrypoints must use ONE analytics service. Both the scheduled
weekly script and Monday ingestion publication must route through it; ingestion
only records/queues work and must not wait for provider calls. Use a durable DB
job with a unique date/version/input key and lease rather than require a new broker.
The existing weekly runner drains/retries work. Persist before publishing and
atomically switch the report revision only after validation completes.

Normal retries reuse the same snapshot and cached outputs. Revised input or
methodology creates a new revision, preserving the previously published one.
Concurrent triggers must not duplicate provider work or race legacy publication.
Keep the last valid revision if regeneration fails and display its freshness.

FR-19. Proposed operational limits: provider concurrency 4; JEV timeout uses the
existing setting; DeepSeek request timeout 60 seconds; at most two retries for
transient errors with jitter and Retry-After; no retry loops for invalid credentials.
Persist progress across runs. A worker processes at most 1,000 uncached JEV
decisions, 100 DeepSeek ambiguity-resolution batches (up to 10 articles each),
and 16 narrative calls per run, within a 15-minute wall-clock budget. Model names,
input/output token caps, and these limits are configurable and versioned.
Budget exhaustion postpones remaining work or marks enrichment incomplete; it
never silently excludes expensive articles from the denominator. Initial backfill
may require multiple runs. Log call/token counts and failures without secrets.

## 11. Acceptance scenarios

The following controlled fixtures use healthy comparable cohorts unless stated.

| ID | Fixture | Required result |
|---|---|---|
| AC-01 | 5 events / 5% share become 12 / 12%, >=3 publishers, >=2 days | Up; +7 pp, +140% |
| AC-02 | 12 / 12% become 5 / 5%, prior supported | Down; -7 pp, approximately -58.33% |
| AC-03 | Volume doubles but topic share is unchanged | Stable, never Up from volume alone |
| AC-04 | Healthy W0 has zero topic events; supported W1 share 8% | Down, -100% share growth |
| AC-05 | Same zero follows a coverage failure breaking retention gates | Insufficient data, never Down |
| AC-06 | Topic wording/language changes while semantic topic and share stay equal | Same ID, stable |
| AC-07 | Duplicate URLs/20 copies of one event within one publisher | One observation; no artificial support |
| AC-08 | One event syndicated by 20 publishers | E=1; not confirmed Up/New |
| AC-09 | Five events, three publishers, two days; absent in healthy 28-day history | New; growth null |
| AC-10 | Same current signal but history missing | Insufficient history, never New |
| AC-11 | Absent W1 but present two weeks earlier | Resurfacing, not New or infinite growth |
| AC-12 | Only 1 -> 2 events or tiny share change | No confirmed Up |
| AC-13 | Add a prolific publisher during W0 | Excluded symmetrically; no artificial Up |
| AC-14 | DeepSeek fails or invents a URL/number/causal claim | Same metrics and sections; template narrative |
| AC-15 | JEV fails without adequate cached classification | Quality reason; no false confirmed labels |
| AC-16 | More than 200 eligible articles, relevant topic below rank cutoff | Count every page; no top-N bias |
| AC-17 | GET, CLI job, and Monday trigger refer to the same input/version | Same snapshot semantics; GET makes no provider calls |
| AC-18 | Stored legacy report, v2 rebuild, concurrent retry | Preserve legacy; atomic versioned publication |
| AC-19 | New taxonomy definition matches historical material | Reclassify H; do not emit false New |
| AC-20 | Current UTC week incomplete or timestamps on window boundaries | Provisional or exact non-overlapping inclusion |
| AC-21 | No qualifying topics despite sufficient data | Informative empty state on page and preview |
| AC-22 | Identical frozen input/assignments/configuration rerun | Identical metrics, direction, ordering, evidence IDs |

## 12. Release criteria, limits, and references

Before enabling v2, replay at least eight completed weeks where coverage can be
established. Review 200 stratified semantic assignments including multilingual,
ambiguous, duplicate, and unseen-topic examples. Target >=90% assignment precision
among accepted assignments and >=90% precision on 50 manually reviewed duplicate
pairs. Inspect every displayed trend in the replay for traceable counts and
citations; audit rejected candidates too, so an always-empty classifier cannot
pass by precision alone. Record sample counts, unresolved rate, section fill rates,
false positives, and missed supported signals. No required section fill quota.

Threshold tuning and evaluation must use separate weeks. If trustworthy historical
coverage is unavailable, collect it prospectively: at least two completed weeks
for Up/Down and 35 observed days for a full New evaluation. Historical previews
remain explicitly unverified. Models can misclassify and the source corpus can
be biased; this design makes decisions inspectable and reproducible, not universally
objective or statistically significant. Statistical trend inference is out of scope
for v2; do not attach p-values or confidence intervals to these heuristic gates.

Official provider documentation checked 2026-10-10:

- [TypeSafe introduction and typed primitives](https://docs.typesafe.ai/introduction).
- [DeepSeek JSON output](https://api-docs.deepseek.com/guides/json_mode/).

Provider API capabilities are documented facts; architecture, thresholds, quality
gates, budgets, and release targets above are this project's proposed design.
