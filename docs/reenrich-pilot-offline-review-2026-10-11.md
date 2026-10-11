# Offline review of held rejects and unclassified accepts

This review uses the completed pilot's frozen source text, saved JEV answers,
probability distributions and existing deletion rules. It makes no provider
requests, source downloads, threshold changes, category assignments, production
writes or modifications to the paid journal. Saved input hashes were verified
unchanged. The findings below are diagnostic hypotheses, not new model decisions.

## The 39 held records are JEV rejects

All 39 received valid answers: 30 `non_editorial`, nine `non_ai`. Their cleanup
outcome is `unresolved` because safe-deletion requirements were not satisfied.
There are no missing provider responses, failed fetches or JEV
`insufficient_evidence` choices within these 39. The original 441 fetch/quality
cases are a separate population and were not part of this pilot sample.

The overlapping failed requirements are:

| Requirement failing | Records |
| --- | ---: |
| Admission confidence below 0.95 | 30 |
| Non-editorial decision lacks deterministic corroboration | 27 |
| Non-AI decision has AI relevance above 0.05 | 7 |
| Source body shorter than 160 characters | 0 |

The exact disjoint breakdown accounts for all 39:

| JEV choice | Failed requirements | Count |
| --- | --- | ---: |
| non_editorial | Confidence and corroboration | 18 |
| non_editorial | Confidence only | 3 |
| non_editorial | Corroboration only | 9 |
| non_ai | Confidence and relevance | 7 |
| non_ai | Confidence only | 2 |

The three safe reject candidates remain unchanged and outside these 39.
These guardrails deliberately preserve records when model confidence or source
corroboration is insufficient. They do not assert that each retained record is
editorial or AI-centred.

Examples from the saved sources explain why those requirements should be kept:

- The [Qodo RAG category page](https://www.qodo.ai/blog/category/rag/), Artillery
  pricing page and vxlang homepage have deterministic page flags, but model
  confidence is only 0.53, 0.63 and 0.73. They fail the confidence requirement.
- The [Redwood RangerAI landing](https://runmyjobs.redwood.com/lp/redwood-rangerai)
  and [Qodo Context Engine feature page](https://www.qodo.ai/features/qodo-context-engine/)
  have clear product-oriented fragments. JEV confidence is 1.00, but the narrow
  existing URL/text filter supplies no corroboration. Nested paths and product
  copy warrant offline eligibility investigation; this is not permission to
  expand deletion heuristics automatically.
- [ExtractBench](https://www.llamaindex.ai/blog/introducing-extractbench) describes
  a benchmark, result tables and a runnable harness, alongside a webinar CTA.
  JEV chose non_editorial at 0.56. It illustrates the risk of treating vendor
  publication or a CTA as sufficient evidence of non-editorial content.
- [Baseten's OpenAI partnership](https://www.baseten.co/blog/baseten-openai-partnership/)
  contains an announcement and integration/performance information as well as
  commercial copy. JEV chose non_editorial at 0.96, but the deterministic rule
  correctly supplies no deletion corroboration. Editorial-versus-promotion
  treatment needs a clearer rubric, not a weaker destructive threshold.
- The [EU AI Act webinar item](https://www.kdnuggets.com/2026/07/airia/could-your-ai-systems-already-be-high-risk-under-the-eu-ai-act)
  centres its saved opening and ending on accessing a webinar. It differs from
  the benchmark's substantive technical material. Legal keywords alone do not
  establish editorial admission.
- The games-bundle deal has non_ai confidence 0.85 and relevance 0.01; it is
  held only by the confidence requirement. Other examples, including financing
  stories, have both lower confidence and greater AI relevance. Apparent human
  clarity in one deal story does not justify changing the global threshold.

## All 13 unclassified accepts have a proposed topic

Every raw category choice is one of the ten agreed topics; none chose `Other`.
All category confidence values are below 0.7. The model's top-option probability
is a separate field: for example, probability 0.72 with confidence 0.69 still
does not pass a confidence threshold of 0.7. These fields were not substituted.

The following table covers all 13. Candidate readings are provisional, based on
bounded beginning/middle/end source fragments and selected relevant passages.
The primary stored topic remains unclassified in every case.

| Saved source | JEV choice / confidence | Strongest competing reading | Offline diagnosis |
| --- | --- | --- | --- |
| [OlmoEarth embeddings](https://huggingface.co/blog/allenai/olmoearth-embeddings) | Models & Research / 0.38 | AI Applications; top probabilities 0.44 / 0.43 | New export/analysis workflow for Earth-observation representations versus a model capability story. This is not retrieval-specific RAG merely because embeddings appear. AI Applications is a plausible reading of the feature workflow; keep it provisional. |
| [Gemini Robotics ER 2](https://deepmind.google/blog/gemini-robotics-er-2-powering-robotics-with-video-understanding-task-orchestration-and-multi-robot-collaboration/) | Models & Research / 0.69 | AI Applications, Agent Frameworks | New reasoning-model capabilities and evaluation versus a robotics domain label. The main object of the announcement suggests Models & Research, subject to review. |
| [Jesse Thaler appointment](https://news.mit.edu/2026/jesse-thaler-named-director-laboratory-nuclear-science-0707) | AI Applications / 0.47 | Other; probabilities 0.52 / 0.39 | Main event is a laboratory directorship; AI/ML occurs in the research biography. Review admission centrality first. Relevance is 0.23 and accept confidence 0.32; a new topical category would not solve this. |
| [Search-result payload breakdown](https://machinelearningmastery.com/2026-09-prnews-io-whats-actually-inside-24723-tokens-of-a-search-result-we-broke-it-down-field-by-field/) | RAG & Data Systems / 0.44 | AI Applications; probabilities 0.49 / 0.43 | Retrieved search-context representation versus general application integration. Distinguish retrieval payload design from model structured-output generation. RAG is a plausible reading, not a new assignment. |
| [Data-science portfolio project](https://www.kdnuggets.com/building-an-end-to-end-data-science-portfolio-project) | AI Applications / 0.47 | Other; probabilities 0.52 / 0.46 | Substantial applied-ML material includes tree models/XGBoost, evaluation and deployment. Review the scope of general ML guides, not simply incidental AI keywords. It is not equivalent to the personnel announcement. |
| [Cyber Risk Discourse](https://www.interconnects.ai/p/the-cyber-risk-discourse-is-broken) | Security & Safety / 0.69 | Policy & Regulation | Analysis of open-model cyber risks and mitigations also discusses bans and national policy. Security & Safety is a plausible main-subject reading; governance references need not determine the topic. |
| [Import AI 468](https://importai.substack.com/p/import-ai-468-23-rsi-ideas-posttrainbench) | Security & Safety / 0.38 | Policy & Regulation, Other | A genuinely mixed research/newsletter packet, including benchmark material, governance and fiction. No clear single dominant topic is established by the bounded input. Keeping it unclassified is an appropriate outcome. |
| [NVIDIA Japan ecosystem](https://blogs.nvidia.com/blog/japan-ecosystem-2026/) | Business & Industry / 0.48 | AI Applications; probabilities 0.53 / 0.47 | Broad ecosystem/industry announcement with numerous deployment examples; commercial strategy versus end-user outcomes. Both the article's breadth and incomplete input are relevant confounders. |
| [Gemini Robotics 2](https://deepmind.google/blog/gemini-robotics-2-brings-whole-body-intelligence-to-robots/) | Models & Research / 0.67 | AI Applications | New model/control capabilities versus robotic deployment. Clarify the primary-object distinction between a model release and an application outcome. |
| [Cosmos-H-Dreams](https://huggingface.co/blog/nvidia/cosmos-h-dreams) | Models & Research / 0.59 | AI Applications; probabilities 0.63 / 0.37 | Training/distillation and action-conditioned world-model methodology versus surgical use. Model methodology is a plausible main subject despite the domain-specific headline. |
| [Dify workflow triggers](https://dify.ai/blog/which-trigger-should-i-use-a-beginner-s-guide-to-starting-dify-workflows) | Agent Frameworks / 0.49 | AI Applications; probabilities 0.54 / 0.45 | General runtime/orchestration primitives illustrated through application scenarios. Agent Frameworks is plausible if runtime mechanics are primary. |
| [NIST generative-AI risk guide](https://www.anaconda.com/blog/nist-ai-600-1-generative-ai-profile-guide) | Policy & Regulation / 0.68 | Security & Safety | Organisational governance/standards guidance overlaps concrete safety controls. Distinguish formal governance framework discussion from implementation of runtime defences. |
| [Groq/Bell partnership](https://groq.com/newsroom/groq-becomes-exclusive-inference-provider-for-bell-canadas-sovereign-ai-network) | Infrastructure / 0.64 | Business & Industry; probabilities 0.67 / 0.33 | Exclusive commercial partnership is the event; inference capacity is context. Business & Industry is a plausible alternative under the agreed main-subject rule. |

Working hypothesis groups: ten topic-boundary/main-subject cases, one mixed
newsletter and two admission/scope checks. These are review classifications,
not measured causal attribution. Four confidence values are 0.67-0.69, but
proximity to the threshold is not a reason to lower it automatically.

Three of the 13 received a truncated source input, although their complete
saved extraction is available locally:

| Source | Full extracted characters | Characters sent |
| --- | ---: | ---: |
| Data-science portfolio | 17,187 | 16,000 |
| Import AI newsletter | 19,133 | 16,000 |
| NVIDIA Japan ecosystem | 28,651 | 16,000 |

The omitted cached tails were inspected in bounded fragments without fetching.
They include author/end matter, additional newsletter sections and further
industry examples. Truncation is a confounder, not proof that these labels would
change with a different input. The other ten had complete extracted text in
the pilot request; their uncertainty cannot be blamed on this input clipping.

## Business & Industry: admission is part of the bottleneck

Six records chose Business & Industry before the final admission/topic filter.
Three were non_editorial, two non_ai, and one accepted with category confidence
0.48. Four of those six raw choices had confidence at least 0.7. Thus the zero
final business-topic count cannot be interpreted as failure to recognise the
category: five records were blocked by admission, the remaining one by topic
confidence. Examples include partnership announcements and AI-company financing.
Topic expansion alone must not reverse existing admission rejects.

The ordinary admission wording accepts AI-centred editorial material and rejects
ads, but gives few concrete distinctions for vendor benchmarks/technical
announcements, company financing and commercial partnerships. Its accepted
choice is currently sufficient to keep a record; there is no separate minimum
accept-confidence/relevance guard. This explains why low-centrality cases can
also appear among accepts. Any admission-policy change requires explicit review;
this audit neither adds such a threshold nor changes outcomes.

## Recommended next preparation

Keep all current numeric thresholds and the ten-topic list. Prepare a versioned
rubric draft with explicit primary-subject examples for model releases versus
domain applications, retrieval-context design versus general integration,
runtime orchestration versus end-user workflows, governance frameworks versus
operational safety, and commercial partnerships versus infrastructure engineering.
Clarify substantive vendor editorial material versus product/webinar landings
and AI-centred business reporting versus incidental company/profile mentions.

Keep mixed newsletters unclassified where no dominant topic is supported. Review
the complete saved text in the three clipped cases and the two admission/scope
cases before proposing another paid comparison. If questions or bounded evidence
change, version/hash the actual request and evaluate a targeted disputed set
with an independent review reference; do not treat the old response as a result
under the new rubric or silently repeat the entire pilot. No new paid comparison
or mass-processing budget is approved by this offline review.

## Receipt and verification

Private audit: `tmp/reenrich-2026-10-11/pilot-offline-guard-category-review.json`.
It covers all 80 saved assessments, names each failed requirement for the 39
held rejects, and records the raw category/probability metadata for all 13
unclassified accepts. SHA-256:
`1cfd0b27c5c2ac85ca4e51223380fe59b9314a2675d5c69fe5cddab83ca79eb9`.
The file is mode 0600 in the existing private run.

Offline assertions verified frozen request identities, valid stored JEV responses,
matching admission fields, exact 39/13 counts, unchanged input/journal hashes and
unchanged provider counts (JEV 80 / DeepSeek 43). Additional provider calls and
spend are zero; cumulative conservative usage-priced cost remains $0.058944.
Production, source cache, paid plans/results, prompts and thresholds are unchanged.
No application code was edited, so no additional pytest/lint run was needed.
