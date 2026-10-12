> **ARCHIVE — historical record, 2026-10-10–12.** Saved prompts, approvals, commands and runtime states are superseded; do not use this file to resume work. See the [archive index](../README.md) for completed outcomes and remaining work.

# Re-enrichment checkpoints, 2026-10-11

Status: pilot and targeted rubric validation complete; final candidate clarification 3;
pilot budget approved, cumulative cost $0.196297; mass budget not approved.
Branch: `feat/reenrich-publication-dates-2026-10-11`.
Source of scope: [saved prompt](prompt-reenrich-and-fix-publication-dates-2026-10-11.md).

The user specified the sequence below and requested explicit stops between
stages. Comparison is agreed as a separate material type, with compared
products recorded separately where available. The ten working topic names are
now accepted; the $1.50 pilot budget is approved (JEV $0.25 / DeepSeek $1.25).
Bulk download/extraction uses an ordinary script without model calls. Keep
the corpus private: Codex receives aggregates and a bounded sample only.
Article model processing is performed by JEV/DeepSeek from cached source text.
No provider calls or article downloads had run at the initial preflight.

## Read-only preflight

Production inspected at `2026-10-10T23:21:57.394570+00:00`
(October 11 in Europe/Warsaw). Private aggregate receipt:
`tmp/reenrich-stage0-production.json`.

| Check | Observed value |
| --- | --- |
| PR #15 | Merged, `2026-10-10T23:09:49Z` |
| Production image | `ghcr.io/orlv-85/ai-parser:v0.1.79` |
| Migration | `f31a640c9b33` |
| Current articles | 7,430 |
| Original unresolved set | 3,681 |
| Unresolved IDs still present | 3,681 |
| Other current articles | 3,749 |
| Previously deleted 1,119 IDs present | 0 |
| Retention environment | 800 days |
| JEV / semantic admission enabled | true / true |
| JEV model / category threshold | `jev-1.13.0` / 0.7 |
| Weekly v2 / active weekly cron | false / 0 |
| Active collector cron | 1 |
| NULL stored publication dates | 0 |
| Discovered on October 4, UTC | 853 |
| Stored publication on October 4, UTC | 580 |

Zero NULL publication dates does not establish that those dates are reliable.
These are baseline counts, not evidence of how many dates need correction.
The remaining 3,749 require an offline provenance audit before determining
the date-only fetch set. Row/evidence/dependency drift has not yet been audited.
The 5/4 GiB thresholds remain constraints; this preflight did not independently
inspect the effective maintenance size thresholds.

Current category counts: 6,508 unclassified; Business & Product 394;
AI Coding 140; Security 113; QA & Observability 99; Agent Frameworks 86;
Infrastructure 58; RAG & Data Systems 32.

## Taxonomy preparation and comparisons

Current taxonomy has seven primary topics in `src/app/core/categories.py`.
Business & Product covers model releases, research, applications, companies
and regulation. Models & Research, AI Applications and Policy & Regulation
are discussion candidates, not approved categories. The business topic and
compatibility with existing Business & Product values also need agreement.

An offline title search in the original saved snapshot found 143 previously
kept rows matching `vs`, `versus`, `comparison` or `compared`. This is a
title-based candidate count, not a validated content-type classification or
a current production count. Public title examples include:

- Claude Haiku 5.5 vs Sonnet 5.5: Which AI Model Should You Choose in 2026?
- Thinking vs Thinking: Benchmarking Claude Haiku 4.5 and Sonnet 4.5 on 400 Real PRs
- Gemini Vs Chatgpt : Benchmarking Ai Models For Software Testing

They illustrate why comparison format can cross model, coding and testing
topics. Agreed representation: one primary topic plus a separate `Comparison`
type and compared products. UI details remain to be specified.
The examples have not been re-fetched or independently reassessed. Titles,
old classifications and summaries do not establish admission or primary topic.

Taxonomy consumers already include JEV, admission cache validation, persistence,
API metadata, UI filters, category sorting, digest groups and exports. Weekly
also references the old categories, but remains off and its frozen reports
must stay unchanged. A new taxonomy requires criteria-aware versioned caching;
old results cannot masquerade as results under new criteria.

## Stages and mandatory stops

| Stage | Deliverable before stopping | Required agreement for next stage |
| --- | --- | --- |
| 0: baseline and sequence | This checkpoint and amended prompt | Completed; user supplied the sequence |
| 1: cache and unpaid bulk download | Tested resumable script; fresh frozen IDs/hashes/dependencies; HTML/text/date evidence or explicit error for all unresolved URLs | Stop with fetch aggregates before topic/sample review |
| 2: representative sample | 50-100 diverse unresolved and previously accepted materials; source-based topic/boundary examples; cost estimate; optional budgeted sample summaries | Working taxonomy, criteria, UI filters/order and pilot monetary caps |
| 3: paid pilot | Combined JEV admission/category, summaries for accepted pilot articles, usage and validation | Mass model pass scope and budget |
| 4: mass models and summaries | JEV admission/category from cached source; DeepSeek summaries for accepted articles; accumulated taxonomy gaps, date-only audit and usage | Review results before apply preparation |
| 5: apply preparation | Exact manifest, current hashes/dependencies, backup, PostgreSQL restore rehearsal and ordinary prune impact | Concrete production apply and schema/release coordination |
| 6: production apply/release | Authorized changes, before/after counts, rollback artifacts and site/runtime checks | Any further scope, including other-article recategorization |

Pilot uses agreed categories and the existing admission policy. Category results
require the agreed criteria and cache version. Paid sample summaries and pilot
costs belong to the new budget. Cached downloads are reused in all later stages.
Summaries derive from source text for accepted articles; summaries are not
destructive decision evidence. Accumulate taxonomy gaps for joint review at
stage boundaries instead of interrupting the pass for each new subtopic.

## Outstanding decisions

- Mass-pass scope and separate monetary budget; sample and pilot are complete.
- Pilot caps are already approved; do not request them again.
- Implementation of accepted working topics; remaining format/UI details.
- Comparison UI filter and product-field details; separate type is agreed.
- Date precision/conflict presentation and downstream behavior, after audit.
- Production schema/release/apply sequence and collector/maintenance coordination.

Stage 1 result: all 3,681 URLs accounted for; 3,533 responses saved, 135 robots
blocks and 13 network errors; 3,240 initial quality passes and 441 unresolved.
All 3,533 saved responses passed offline cache verification. Model calls and
production data changes are zero. See the
[completed fetch report](../../../reenrich-fetch-report-2026-10-11.md) for private artifact
paths, hashes, date evidence counts and scoped validation. No commit, push or
draft PR was created. Next stop is representative sample/topic review; paid
work still requires a monetary budget.

Stage 2 result: bounded exploratory source review of 92 materials (40 previously
kept, 52 freshly extracted unresolved; 70 hostnames). No new summaries or paid
provider calls; no new downloads or production edits. The
[topic proposal](../../../reenrich-taxonomy-proposal-2026-10-11.md) defines ten primary
topics, separate Comparison/product metadata, boundaries, legacy/UI behavior,
versioning and an 80-record pilot. The user accepted the ten working topics
and separate Comparison. Latest proposed pilot total is $1.50, awaiting budget
agreement; separate provider caps are unset. Earlier $0.50/$0.25 proposals are
superseded. Other format/UI details remain proposed, and no paid calls have run.
New test/tool development was not part of this sample-review stage.

Pilot preparation result: the cache was reverified offline (3,533 responses,
zero errors) and an 80-record pilot was frozen in the same private run: 52 fresh
texts, 28 accepted diagnostic controls, 60 hostnames. The resume-safe provider
journal and separate source-grounded summary path are implemented. Provider
calls remain zero. Proposed provider caps are JEV $0.25 / DeepSeek $1.25 within
the proposed $1.50 pilot total; confirmation is pending. See the
[pilot preparation report](../../../reenrich-pilot-preparation-2026-10-11.md).
Prefer DeepSeek over Codex for textual article analysis, as the user reiterated.
The next stage is the paid pilot, followed by another explicit stop.

Paid pilot checkpoint: user confirmed $1.50 total, JEV $0.25 and DeepSeek $1.25.
The pilot ran once and stopped at 21/80 after DeepSeek reached its 300-token
output cap. Results: 4 accepted, 2 reject candidates, 15 unresolved, 3 complete
summaries, 59 unassessed. Conservative usage-priced total is $0.006208; no
unknown billing, repeat payment, source download or production change. See the
[paid checkpoint](../../../reenrich-pilot-checkpoint-2026-10-11.md). Stop before explicit
recovery of the truncated response and continuation of the same pilot; its
budget remains approved and no mass-processing approval is implied.

Stage 3 completed after the user's explicit continuation instruction: 80/80
assessed, 38 accepted with 38 summaries, 3 conservative reject candidates and
39 unresolved. JEV made 80 requests; DeepSeek made 43 including five retained
superseded attempts. Conservative cumulative usage-priced cost is $0.058944.
No completed request was repaid and no source URLs were redownloaded. Source
and paid-plan hashes remain unchanged. See the
[final pilot report](../../../reenrich-pilot-results-2026-10-11.md). The next checkpoint
is pilot boundary/quality review and a separate mass budget, before Stage 4.

Offline review completed on the user's request without provider calls. All 39
held cleanup outcomes are valid JEV rejects (30 non_editorial, nine non_ai).
Failed requirements overlap: confidence 30, deterministic corroboration 27,
non-AI relevance guard seven. All 13 unclassified accepts have named raw topic
choices below confidence 0.7; bounded source review identifies working
hypotheses of ten topic boundaries, one mixed newsletter and two admission/ML
scope cases. Thresholds, stored results, paid journal and production are
unchanged. See the [offline review](../../../reenrich-pilot-offline-review-2026-10-11.md).
Next preparation is explicit rubric/admission clarification before any targeted
paid validation or mass pass; a separate mass budget is still required.

Targeted validation is now complete, as authorised by the user's continuation
instructions inside the approved cumulative pilot budget. DeepSeek drafted the
rubric and independently reviewed saved source inputs; JEV ran three versioned
passes (64, 35, 35 records). Final candidate `pilot-rubric-clarification-3`
gives nine of the original 13 unclassified accepts matching confident topics;
one is non_ai without deletion confirmation and three remain unclassified.
All nine positive controls and the three original safe reject IDs are preserved.
Five admission disagreements remain. Thresholds and Comparison are unchanged.
This diagnostic agreement is not a corpus accuracy estimate or ground truth.

Cumulative original pilot plus validation: JEV 214 calls / $0.030643;
DeepSeek 114 calls / $0.165654; total $0.196297, conservatively usage-priced.
The original approval and shared journal are retained; no unknown/inflight/failed
calls, new downloads or production changes. See the
[validation report](../../../reenrich-rubric-validation-2026-10-11.md) and
[exact candidate questions](../../../reenrich-jev-rubric-clarification-2026-10-11.json).
The [saved context](../session-context-reenrich-2026-10-11.json) and
[short resume prompt](prompt-resume-reenrich-2026-10-11.md) capture this handoff.
Next stage: prepare the mass scope and separate estimate, reusing compatible
paid results, summaries and existing source cache. The pilot caps require no
repeat approval; mass processing and production apply remain later checkpoints.
