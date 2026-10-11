# JEV/DeepSeek pilot completed: 80 of 80

The user authorised continuation of the partial pilot within the already
confirmed $1.50 total / JEV $0.25 / DeepSeek $1.25 caps. All 80 frozen records
have now been assessed, and all 38 accepts have a saved English summary.
Source URLs were not downloaded again. Production data and settings were not
changed. The next checkpoint is review and a separate mass-processing budget.

| Pilot result | Fresh unresolved sources | Accepted diagnostic controls | Total |
| --- | ---: | ---: | ---: |
| Assessed | 52 | 28 | 80 |
| Accepted | 12 | 26 | 38 |
| Conservative reject candidates | 3 | 0 | 3 |
| JEV rejects held by deletion guards | 37 | 2 | 39 |
| Complete summaries | 12 | 26 | 38 |

There are 17 Comparison records and 21 accepted records flagged for topic or
format boundary review. The sample is deliberately selected, not a random
accuracy/prevalence sample. Two previously accepted controls remain unresolved;
none is a confirmed reject candidate. No deletion or cache mutation is performed
by the pilot. All 441 original fetch/quality-unresolved cases remain in scope.

Clarification from the subsequent [offline review](reenrich-pilot-offline-review-2026-10-11.md):
all 39 held records have valid JEV reject choices (30 non_editorial, nine non_ai).
They failed destructive corroboration/confidence requirements; these are not
39 download failures or model insufficient_evidence answers. All 13 unclassified
accepts chose a named topic with confidence below 0.7; none chose Other.

## Topics and summary validation

| Primary topic among accepts | Count |
| --- | ---: |
| AI Applications | 4 |
| RAG & Data Systems | 4 |
| Agent Frameworks | 4 |
| Models & Research | 3 |
| QA & Observability | 3 |
| AI Coding | 2 |
| Infrastructure | 2 |
| Security & Safety | 2 |
| Policy & Regulation | 1 |
| Business & Industry | 0 |
| Unclassified | 13 |

The 0.7 primary-topic confidence threshold was retained. Thirteen accepts
remain unclassified instead of receiving forced labels. No confident Business
& Industry assignment appeared in this pilot, so its boundaries still need
review alongside the other ambiguous cases. These counts are model assignments,
not an independent measure of correctness or justification for changing taxonomy.

Every retained summary fact has a verified exact source quote. If DeepSeek
rendered source line breaks as spaces, the validator maps only whitespace changes
back to the literal source substring and preserves the provider's original quote.
Omitted/altered words are not accepted. All saved compared product names occur
in their verified supporting quote. One unsupported product name remains
unknown; its comparison metadata is marked partial rather than inventing a name
or discarding an otherwise grounded summary. Raw responses remain private.

The suggested 80-word summary length is advisory; twelve longer summaries are
flagged for review. Exact quote presence does not prove semantic entailment:
factual support and topic/comparison quality still require pilot review.

## Recovery and cumulative cost

The source plan, original paid pilot plan, approval and SQLite journal were
preserved. Existing JEV assessments and complete summaries replayed without
new requests. The original 300-output-token restriction was replaced with room
for a complete structured response; non-thinking mode remains explicit. Known,
billed quote failures received one narrower grounded repair request. Unknown
billing and provider outages still stop dispatch, without automatic retries.
Changes to length handling and quote whitespace mapping were applied offline
to saved responses wherever possible.

| Provider | Requests | Conservative usage-priced dollars |
| --- | ---: | ---: |
| JEV | 80 | $0.010636 |
| DeepSeek | 43 | $0.048308 |
| Total | 123 | $0.058944 |

DeepSeek's 43 requests include 38 retained summaries and five superseded,
known billed attempts retained in the journal. Three retained summaries use
prompt version 1, 31 use version 2 and four use the narrower quote-repair
version 3. There are zero failed/inflight/unknown-usage calls at completion.
Completed requests were not paid again.

Dollar amounts are computed from usage at the previously checked
[JEV rate](https://docs.typesafe.ai/models) and
[DeepSeek peak/cache-miss rates](https://api-docs.deepseek.com/quick_start/pricing/),
rounded up per request. They include the superseded attempts and are not a
provider invoice. The approved pilot caps remain unchanged; unused headroom
does not authorise mass processing.

## Private artifacts and verification

Run directory: `tmp/reenrich-2026-10-11`, reused throughout. Source content,
supporting quotes and model responses were not printed into Codex context or Git.
The original source plan/sample and frozen pilot plan retain their hashes.
The earlier 21/80 report/results/usage are archived as
`pilot-*-before-recovery.json`; the original incomplete response remains in
`pilot-journal.sqlite3`, alongside all repairs and review reasons.

| Artifact | SHA-256 |
| --- | --- |
| `pilot-plan.json` (unchanged) | `af251a13e7cded1d7a126d7c65e7cdee9ed660e87b79c39b2d973530b2a7405f` |
| `pilot-report.json` | `e18c8cf5328f23afb3445be4f14a2dbedc565c2e2d032521a8cbf5e334a86025` |
| `pilot-results.json` | `242b23fcba7242015e1ac8dbbd8fe9caf8e3e4311a30499c6b5f83d78ad3aa46` |
| `pilot-usage.json` | `f3f14200cee52bf9a925256a179551ff5c00115c1a272c32b0f55880541efa56` |
| `pilot-budget-approval.json` (unchanged) | `0cfa325341f707db95c6d2de914128309bc7e7aea53e3ca96b079dba3d5f503e` |
| `pilot-summary-revision.json` | `0ebab4b571ebe39bd90ae73313a6f5dbd350486c05092d1a18cbe68f233b7e5c` |

Final offline validation checked the exact 80 unique IDs against the frozen plan,
presence of a summary for every accept, literal source membership of all retained
quotes/product names and unchanged source plan/sample hashes. No corpus output
or model payment was needed for these checks.

Scoped validation: 92 tests passed, including the ordinary JEV/admission/cleanup
regressions and recovery/grounding tests. Ruff passed for src/tests and the
re-enrichment scripts; mypy passed for 143 source files; scoped pylint passed
at 10.00/10. Full `make lint`, full pytest and PostgreSQL restore/apply checks
were not run: no commit/push, schema release or production apply occurred.

Next: review the accumulated topic/format boundaries and the partial product
metadata, then prepare the mass pass using the same saved sources and compatible
pilot responses. Mass monetary limits remain unapproved. Weekly stays off;
retention, prune thresholds, frozen reports and production data are unchanged.
