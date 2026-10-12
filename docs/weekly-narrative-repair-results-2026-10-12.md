# Weekly explanations repair: 2026-10-11 report

All eight previously selected narratives now have source-supported English
explanations: **8 accepted / 0 held**, with 20 accepted factual claims. Four proposed
claims were discarded. The other 17 topics remain their original templates and
were never selected for new narrative calls. The report mode is honestly `mixed`.
All 25 topic states remain `insufficient_evidence`; the report remains
`insufficient_data`, with no confirmed New, Up or Down topics.

## Proven causes and correction of the earlier diagnosis

Read-only replay matched each original packet to its weekly cache key and durable
request key. The private receipt retains those keys and complete size aggregates.

| Topic | Original complete request bytes | Actual original rejection |
| --- | ---: | --- |
| agent-tooling | 16,438 | Local pre-dispatch input cap; no provider request |
| enterprise-agents | 16,629 | Local pre-dispatch input cap; no provider request |
| robotics | 16,715 | Local pre-dispatch input cap; no provider request |
| open-models | 16,925 | Local pre-dispatch input cap; no provider request |
| language-models | 12,661 | `finish_reason=length`; incomplete JSON at output cap 1,200 |
| safety | 11,700 | **9 claims**, exceeding the validator's maximum of 6 |
| security | 15,889 | **9 claims**, exceeding the validator's maximum of 6 |
| coding-agents | 15,227 | **7 claims**, exceeding the validator's maximum of 6 |

The previous description of three empty claim lists was incorrect. The old
validator used the same return line for empty, invalid and excessive lists;
actual saved responses and parsed cache entries prove these lists were nonempty.
The old prompt never specified the six-claim limit. The truncated response had
5,031 content characters and required duplicate explanation/claim text.

Evidence dominated request size: 9,967-15,051 serialized bytes, versus 387-410
bytes of metric metadata. URL/source framing and escaping mattered as well.
Navigation-marker counts were low (mostly zero, occasionally one), a heuristic
rather than a semantic certification. Real DeepSeek/JEV calls subsequently found
concrete source facts; no new fetch, reconstructed coverage, or excerpt expansion
was needed.

During repair, a compound JEV question introduced another rejection: source facts
were judged together with language, date attribution and an insufficient trend
state. A limited diagnostic probe gave factual entailment 0.92-0.94 and English /
absence-of-inference above the gate, while its temporal question scored 0.15-0.20
even for sentences without explicit week assertions. Separate source-only factual
checks now pass. The individual effects of the old state and question wording
were not separately isolated; this is not claimed as the cause of the original
three rejections, which occurred before JEV.

## Delivered behavior

- Narrative-specific prompt version `weekly-narrative-5`, full serialized request
  byte cap 16,000, and output cap 2,400 tokens. Global classification caps and
  classification cache keys remain unchanged.
- A compact packet carries the topic definition, state, quality reason and at
  most six existing literal source excerpts. It removes duplicated metric/URL
  framing and reserves space for instructions, escaping and one corrective request.
  It trims source spans rather than serialized JSON, preserving evidence IDs.
- Output is a topic ID and 1-3 claims with evidence references and literal quotes.
  Code assembles the explanation from accepted claims and adds the honest coverage
  limitation. Previous-week reporting is labeled from immutable evidence metadata;
  publication week does not establish when an event occurred.
- Literal quote, numeric, reference, schema, finish-reason and language checks
  remain. JEV separately checks factual support, English and unsupported inference;
  **every retained claim passes every gate at >=0.85**. Unsupported claims are
  discarded and their scores remain in diagnostics. These scores verify semantic
  source support, not independent truth of reported events.
- Technical rejection codes distinguish input size, truncation, empty/excess
  claims, schema, quotes, numbers, English, support and provider availability.
  One corrective attempt is bounded; run-budget exhaustion propagates as a pause.
  Accepted results have their own versioned validation cache, and the prompt
  version also changes the durable provider request identity.
- `revise-narratives` freezes a separate revision, copying complete paid journals
  and caches. It never calls admission, classification, clustering or the calculator.
  Exact invariant/hash checks protect publication; an expected previous pointer
  can reject concurrent target drift under the date lock.

## Real eight-topic result

| Topic | Accepted claims | Discarded claims | Minimum accepted gate | Held / corrective reason |
| --- | ---: | ---: | ---: | --- |
| agent-tooling | 3 | 0 | 0.90 | None |
| language-models | 3 | 0 | 0.93 | None |
| safety | 2 | 1 | 0.90 | None |
| enterprise-agents | 2 | 1 | 0.88 | None |
| robotics | 3 | 0 | 0.85 | None |
| open-models | 2 | 1 | 0.90 | One corrected `invalid_quote` |
| security | 3 | 0 | 0.89 | None |
| coding-agents | 2 | 1 | 0.85 | None |

The first accepted three covered pre-dispatch oversized, truncated and excessive
claim cases. Resume reused them before processing the remaining five. The final
presentation revision reused all eight accepted responses with no credentials
and **zero further model calls**. Safety's retained facts are previous-week
context and explicitly labeled as such; no current-week safety event is invented.

## Limited before/after examples

### Agent tooling

Before: Observed event groups: 10 to 15. Trend confirmation is unavailable;
growth, decline and novelty are unconfirmed.

After, first accepted claim: Postman described building Agent Mode, an AI-native
way to work across API testing, documentation, discovery, and implementation,
running on Amazon Bedrock.

Source: [AWS/Postman](https://aws.amazon.com/blogs/machine-learning/how-postman-runs-agent-mode-for-40-million-developers-on-amazon-bedrock).

### Language models

Before: Observed event groups: 10 to 13. Trend confirmation is unavailable;
growth, decline and novelty are unconfirmed.

After, first accepted claim: Anthropic released Claude Haiku 5.5, with pricing
starting at $0.10 per million input tokens and $0.50 per million output tokens for
requests below 100,000 tokens.

Source: [VentureBeat](https://venturebeat.com/technology/anthropic-launches-claude-haiku-5-5-with-90-api-price-reduction-matching-gpt-6-luna).

### AI safety

Before: Observed event groups: 4 to 7. Trend confirmation is unavailable;
growth, decline and novelty are unconfirmed.

After, first accepted claim: Previous-week reporting: David Robinson resigned
from OpenAI and wrote in The Atlantic that the company's "culture is broken,"
saying he led writing of safety reports for major product launches.

Source: [TechCrunch](https://techcrunch.com/2026/10/03/openai-safety-employee-resigns-claiming-the-companys-culture-is-broken).

Each full explanation also states: "Comparable coverage is insufficient to
confirm an attention trend." These are limited examples from the frozen sources,
not new independent reporting or verified market developments.

## Preservation, lineage and validation

The invariant comparison is exact over all non-prose fields: 932 assignments,
dates and publication precision, admission, event IDs, complete scope, cohort,
denominators, counts, unavailable metrics, all states, thresholds, evidence and
quality facts. All 17 unselected items are byte-equivalent as parsed objects.
The original r4 candidate, database and journal byte hashes remain unchanged.

Original private root:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r4`.
Final private root:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-narratives-20261011-r10`.
Intermediate r5-r9 roots remain retained, including rejected paid responses and
diagnostic probes; r6 was prepared but not dispatched. Lineage and copied caches
retain every attempt and the inherited reviewed transport reserve.

- Parent candidate SHA256:
  `750be9c70ceffb88890c5557fd651c609451a344ddb7800a35fd936c74aac7ba`.
- Final candidate SHA256:
  `65896bd45294d3138d408ab0fedb02522d9c2500c9f8f1e658680e6ed5d5e63a`.
- Final snapshot:
  `933f4c67f1bc4f14513b87fed58a1dc129dc1ee3e3d386dce208d1d46ad011d5`.
- Private receipts: `verification.json`, `diagnostics-original.json`, `frozen.json`,
  `usage.json`, `parent-candidate.json`, `journal.sqlite3`, `weekly.sqlite`.
- Scoped narrative/frozen tests passed; final repo-wide
  `make lint PYTHON=./venv1/bin/python` passed (ruff/mypy/pylint).
- Final repo-wide pytest: **883 passed, zero skips**, using isolated SQLite and
  UTF-8 PostgreSQL on a private Unix socket. An initial absolute SQLite override
  caused unrelated tests to share data; the relative test-local configuration
  corrected this environment issue, without changing application code.
- Real completed-run replay preserved the candidate hash with zero dispatches.
  Separate SQLite publication used the regular verified publisher with zero
  dispatches. Tampered metrics and pointer drift are covered by regressions.

Repair usage: **$0.025418 incremental usage-priced peak estimate (18 DeepSeek / 42 JEV requests); $0.527349 cumulative commitment including the inherited $0.005059 unknown reserve, not an invoice.**

## Delivery record

Base PR #23 was merged into `e03b057`; production was verified on v0.1.87 with
no v2 publication, no snapshots for the target date, no leased weekly jobs, and
v2 visibility disabled. Delivery details, target backup, CI, release and live
API/page verification will be appended after the normal release/publication flow.
