# Primary topic proposal after bounded source review

Status: user accepted the ten working topics and Comparison as a separate type.
No production taxonomy or provider processing has changed. Stage 2 follows the
completed unpaid download. The latest proposed pilot total is $1.50, awaiting
explicit budget agreement; earlier $0.50/$0.25 figures below are superseded.
Per-provider pilot caps and the other format/UI details remain to be finalised.

## Evidence sample

The private sample contains 92 unique articles: 40 previously kept articles
with saved content and 52 unresolved articles with freshly cached source text,
from 70 hostnames. The initial 80 examples balanced existing category labels,
title signals, comparisons and negative controls. Twelve additional examples
checked policy, business and application boundaries. Sampling used metadata;
topic discussion used bounded source excerpts from the beginning, middle and
end. No complete corpus or complete articles were loaded into Codex.

This is a deliberate coverage sample, not a random sample for estimating topic
prevalence or accuracy. Old content for the 40 accepted examples has not been
independently refreshed or validated as factually current. Fragment review is
exploratory; JEV must make the actual source-based admission/category decisions.
No new summaries were generated and no provider requests were made.

Private sample: `tmp/reenrich-2026-10-11/taxonomy-sample.json`.
Full HTML/text remain private; this proposal contains only criteria and public
title/URL references, not source article excerpts.

## Proposed topics and display order

One primary topic per admitted article. Article format is separate.

| Order | Topic | English classification criterion |
| --- | --- | --- |
| 1 | Models & Research | AI model releases, architectures, capabilities, training methods and foundational AI research. General-purpose model comparisons belong here. Research focused primarily on security, retrieval, evaluation tooling or another specific topic belongs to that topic. AI used to advance another scientific field belongs to AI Applications. |
| 2 | AI Coding | AI-assisted software development, coding assistants, coding agents, code generation/review and integration of models into developer coding workflows. Exclude funding stories, underlying kernel/inference engineering and general agent platforms when those are the main subject. |
| 3 | Agent Frameworks | Agent orchestration, planning, tool use, MCP, memory coordination, general agent platforms and automation runtimes. Coding-specific workflows belong to AI Coding; retrieval mechanisms to RAG & Data Systems; domain-specific deployment outcomes to AI Applications. |
| 4 | RAG & Data Systems | Retrieval, embeddings used for retrieval, vector databases, document parsing for AI, knowledge stores and retrieval/data pipelines. A product serving end-user search is AI Applications when its user outcome is the main subject. General foundation-model embeddings or robotics representations do not automatically constitute RAG. |
| 5 | QA & Observability | Evaluation methodologies, test harnesses, reliability measurement, hallucination detection, tracing and monitoring of AI systems; substantive AI-centred software testing practices and testing agents. Benchmark numbers incidental to a model/product release do not change its topic. |
| 6 | Security & Safety | AI attacks, jailbreaks, prompt injection, vulnerabilities, defensive controls, provenance, alignment and harmful capability/misuse risks, including biosecurity. Laws and governance obligations belong to Policy & Regulation; generic non-AI cyber news is not admitted merely because the label says Security. |
| 7 | Infrastructure | AI compute, chips, serving, inference optimization, distributed training systems, compilers/kernels, data centres and AI compute economics. Exclude retrieval-specific pipelines and primarily financial company announcements. The publisher or coding-model brand does not determine the topic. |
| 8 | AI Applications | AI-centred end-user products and practical use in healthcare, robotics, science, education, enterprise work, search and other domains. General LLM application integration, prompting and structured-output practices are subtopics here unless another technical topic is primary. Exclude company financing, fundamental model-method research and general non-AI product news. |
| 9 | Business & Industry | Financing, acquisitions, corporate strategy, commercial partnerships, industry economics and organisational adoption when AI is central and the economic/organisational event is the main subject. Technical product/model releases belong to their specific topics. |
| 10 | Policy & Regulation | AI laws, copyright, litigation, public governance, formal standards, accountability and compliance obligations. A government agency using an AI product is AI Applications unless the article primarily discusses rules or governance. Runtime implementation of monitoring/defences belongs to QA or Security where that is the main subject. |

Prompting and structured outputs do not create an eleventh topic in this
proposal. They are application-engineering subtopics of AI Applications.
New poorly fitting subtopics are accumulated for joint review at checkpoints.

## Observed boundaries and examples

| Stored source example | Proposed interpretation / boundary |
| --- | --- |
| [Modular Manifolds](https://thinkingmachines.ai/blog/modular-manifolds/) | Models & Research, material type Research: neural-network training mathematics. |
| [Claude Opus 5.5 vs Claude Sonnet 5](https://emergent.sh/learn/claude-opus-5-5-vs-claude-sonnet-5) | Models & Research, type Comparison; compared models in a separate field. The stored title is used as an example, not verification of its model claims. |
| [Does Jev make AI code review more efficient?](https://www.qodo.ai/blog/does-jev-make-ai-code-review-more-efficient/) | AI Coding + Comparison: code-review workflow is central; mentioning evaluation does not automatically mean QA tooling. |
| [Firecrawl vs Skyvern](https://www.skyvern.com/blog/firecrawl-vs-skyvern-breakdown/) | Agent Frameworks + Comparison when agent/browser runtime architecture is central. Presence of a comparison does not determine the admission decision. |
| [Constella: swap query models without re-embedding](https://qdrant.tech/blog/constella-research-preview/) | RAG & Data Systems + Research: retrieval-specific embeddings remain retrieval despite a model release. |
| [ExtractBench](https://www.llamaindex.ai/blog/introducing-extractbench) | QA & Observability: an evaluation benchmark/harness for document extraction. |
| [AutoDefense](https://microsoft.github.io/autogen/0.2/blog/2024/03/11/AutoDefense/Defending%20LLMs%20Against%20Jailbreak%20Attacks%20with%20AutoDefense) | Security & Safety: jailbreak defence is primary, despite using agents. |
| [Mixture-of-Kittens](https://cursor.com/blog/mixture-of-kittens) | Infrastructure: a training megakernel, despite being published by a coding vendor. |
| [AI in Healthcare](https://www.linguamatics.com/blog/himss-ai-healthcare-northshore-sdoh) | AI Applications: clinical deployment/use, not foundational AI research. |
| [Structured Outputs](https://humanloop.com/blog/structured-outputs) | AI Applications: integrating model outputs into practical applications. |
| [Lovable financing](https://techcrunch.com/2026/08/12/lovable-confirms-new-13-3b-valuation-raises-another-400m/) | Business & Industry: financing is the subject, despite a coding product. |
| [Claude for Government](https://claude.com/blog/claude-for-government-is-now-generally-available) | AI Applications: availability/deployment for agency users; government is not itself a policy topic. |
| [Govern the decision, not the model](https://rainbird.ai/govern-the-decision-not-the-model) | Policy/governance versus application implementation boundary; include in pilot rather than pretend fragment review resolved all ambiguity. |
| [AI governance monitoring](https://www.tines.com/blog/ai-governance-monitoring-how-to-prove-your-program-is-actually-working/) | QA & Observability versus Policy boundary: monitoring execution versus governance obligations. Include in pilot. |

References above identify saved evidence examples. Their dates, model numbers,
performance results and legal assertions have not been independently verified.

## Format, compared products and admission

Comparison is a separate material type, already agreed by the user. Proposed
format choices: News, Research, Tutorial / Guide, Review, Comparison, Commentary.
Use Comparison for substantive side-by-side assessment of alternatives, including
ranked alternatives/list comparisons, not for any incidental 'vs' phrase.
Store compared product/model names separately, grounded in source evidence;
missing or unclear entities remain unknown. For example: AI Coding / Comparison /
Cursor, GitHub Copilot. Security papers can be Security & Safety / Research.

Advertorial, pricing, homepage, catalogue and About status are admission/quality
issues, not new topical categories. In the reviewed sample, a Qodo category
listing, an app-store listing, pricing and product pages passed the initial
extraction check because they contained text. Existing deterministic URL flags
identify 76 such URL patterns among 3,240 extraction passes: 25 taxonomy pages,
20 site homes, 23 directories and eight corporate pages. Neither those flags
nor this proposal authorise deletion. Confirmed destructive decisions still
require the existing conservative JEV policy, source evidence and later apply
guardrails. Sponsored labels or vendor calls to action alone are not rejection
grounds for otherwise substantive AI editorial material.

Unknown/low-confidence primary topics remain explicitly unclassified.
No random assignment or application of an old keyword fallback should be
presented as a result under this new taxonomy. Keep the current category
confidence threshold of 0.7 as the initial pilot setting, independently of
admission. Mixed newsletters use the editorial lead/dominant subject when
clear; otherwise remain unclassified and join the boundary-case review batch.

## Old-value mapping, consumers and cache

AI Coding, Agent Frameworks, RAG & Data Systems, QA & Observability and
Infrastructure keep their names. Security has proposed new label Security &
Safety, with old Security values retained as legacy values. Business & Product
splits into Models & Research, AI Applications, Business & Industry and Policy
& Regulation based on the source subject; the old string cannot be mapped to
one new topic by a mechanical rename.

Retain existing stored values and published/frozen digest/weekly content.
Only re-enriched accepted articles in the agreed operation receive new labels;
the 40 accepted sample controls are diagnostic, not authorised for broad
recategorization. APIs/exports expose new topic/type/product provenance as
additive metadata. UI: All topics, the ten topics in the proposed order,
Unclassified and a visible legacy-category option; separate material-type
filter; compared products as metadata rather than competing topics. Category
sorting follows the proposed order, then legacy/unknown values.

Proposed taxonomy version: `article-topics-2` (draft until criteria agreement).
Hash the actual topic definitions, ordering and format criteria into category
cache/provenance. Keep admission policy unchanged; expanding topics must not
reopen unchanged old rejects by itself. Combined JEV calls must use cache keys
that distinguish their actual questions and bounded source evidence. Summary
generation has its own cache key and must not change the JEV evidence key.
Weekly stays off; no frozen reports or old weekly taxonomy replay is in scope.

## Proposed paid pilot and estimate

Suggested pilot: 80 distinct records sampled from the 92 coverage examples,
including accepted controls, substantive fresh texts, boundary cases and
non-editorial controls. Admission and agreed primary topic run together in one
JEV request. DeepSeek summaries run only for pilot accepts. This selection
differs from the production apply scope: accepted controls are diagnostic.

Latest proposed cumulative pilot cap: total $1.50, not yet approved. Separate
JEV/DeepSeek caps remain to be set within that total; the earlier proposal of
$0.50 total / $0.25 per provider is superseded.
No money has been approved or spent on providers for this stage. Journal
reservations before dispatch, returned usage and unknown outcomes; do not
silently retry failed/unknown paid attempts. Start conservatively with at most
two concurrent JEV requests and one DeepSeek request. Stop new calls on outage.

Verified official published rates on 2026-10-11:

- JEV `jev-1.13.0`: $0.042 per million input tokens, output free. Public limits
  are 100K input tokens/s and 80 requests/s and can change. [TypeSafe models](https://docs.typesafe.ai/models).
- DeepSeek `deepseek-flash`: peak cache-miss input $0.30/M and output $1.20/M;
  off-peak rates are half. Published Flash concurrency is 2,500. Estimate at
  peak/cache-miss rates regardless of cheaper schedule/cache opportunities.
  Account balance/entitlements have not been checked. [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/).

Rough pilot usage estimate is under $0.20 for 80 combined JEV assessments and
at most 80 short summaries. This assumes bounded source text (up to 16,000
characters), approximately 1 token/4 characters, moderate instruction overhead
and a non-thinking summary capped at 300 output tokens. It is not a provider
invoice or guaranteed upper bound; enforce the dollar caps rather than rely
on this estimate.

For scale context, the 3,240 extraction passes contain 17,841,873 bounded
source/title characters, roughly 4.46M source tokens under that heuristic.
JEV at that scale is roughly $0.30-$0.60 including questions. If every one of
those records were accepted, DeepSeek input plus 300-token summaries is roughly
$2.80 at peak rates with 300 input instruction tokens per item. Actual accepted
count and tokenisation are unknown, and quality flags must be reconciled before
the mass model pass. The remaining 441 unresolved cases are not silently removed
from the overall 3,681-ID scope. Date-only assistance, recovery and other scope
changes need their own volume estimate within a later agreed total budget.

## Agreement requested

The ten working topics and separate Comparison type are accepted. Finalise
remaining format/UI details and approve or adjust the proposed pilot-only
$1.50 total with separate JEV/DeepSeek limits. No mass budget is inferred from
pilot agreement. Implementation and the paid pilot remain the next stage,
with a stop after pilot results before the mass model pass.
