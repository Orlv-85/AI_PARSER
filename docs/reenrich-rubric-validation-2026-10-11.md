# Clarified JEV rubric and targeted pilot validation

The user requested actual JEV/DeepSeek validation without further approval
pauses for small provider calls. It ran within the already confirmed cumulative
pilot caps: $1.50 total, JEV $0.25 and DeepSeek $1.25. No mass pass, source
download, production update or replacement of the original pilot results occurred.

The final candidate is `pilot-rubric-clarification-3`. Its exact tested questions,
model, topic order and unchanged thresholds are saved in
[the reusable rubric JSON](reenrich-jev-rubric-clarification-2026-10-11.json).
Question-set fingerprint:
`19011af1ca5ca9b60b13b19bfcd27d3a87c8555fe8a5090d683971cbbb3799a0`.
This is a validated pilot candidate, not the active production admission policy.

## Clarifications

The ten topics, separate Comparison question, confidence threshold 0.7,
reject confidence 0.95, non-AI relevance maximum 0.05 and destructive
corroboration rules remain unchanged. The wording now states explicit priorities:

- A model architecture, capability or training-theory release belongs to Models
  & Research even in robotics/medicine; practical deployment outcomes and
  application features belong to AI Applications.
- Specific technical subjects take precedence: retrieval-specific embeddings
  and query models remain RAG; evaluation harnesses remain QA; security-centred
  research remains Security; serving/kernel/compiler engineering remains
  Infrastructure. A release or research label alone does not override this.
- General agent tool-use/runtime/behaviour studies remain Agent Frameworks;
  a specific end-user task or domain deployment belongs to AI Applications.
- Formal governance/standards frameworks belong to Policy; operational attacks,
  defences and risk analysis belong to Security when that is the main subject.
- Financing and exclusive commercial partnerships belong to Business & Industry
  when AI is the economic subject; inference-systems engineering belongs to
  Infrastructure. Business news need not explain an AI algorithm.
- Substantive classical-ML guides, including training/evaluating/deploying
  existing algorithms for a practical task, qualify for admission and can use
  AI Applications. A personnel biography with incidental AI and general product
  news with incidental AI do not qualify merely through names or keywords.
- Vendor authorship, sponsorship, commercial tone or a CTA alone do not reject
  substantive editorial material. Feature/benefit/sales, pricing, catalogue,
  store/about and webinar-registration pages still fail editorial admission
  when they lack an independently useful editorial or technical account.
- Mixed newsletters without a dominant subject may remain Other/unclassified.

## Validation sequence

DeepSeek drafted the questions. JEV then classified saved original source
states, while DeepSeek independently reviewed the same states without JEV
predictions. Generated summaries were excluded from both providers' admission
evidence. Actual question/evidence bodies determine the new cache keys.

Version 1 used all 39 held rejects, all 13 unclassified accepts, three prior
safe reject candidates and nine confidently classified positive controls:
64 distinct records. Versions 2 and 3 used 35 records: the 13 category cases,
version-1 admission disagreements and the same positive/negative controls.
The original source inputs remained identical across the comparison; the three
previously clipped source inputs were not silently extended in this experiment.

| Version | Records | Old 13 now with confident accepted topic | JEV/DeepSeek admission agreement | Verified reference quotes |
| --- | ---: | ---: | ---: | ---: |
| Clarification 1 | 64 | 8 | 52/64 | 57/64 |
| Clarification 2 | 35 | 9 | 29/35 | 35/35 |
| Clarification 3 | 35 | 9 | 30/35 | 35/35 |

Version 2 weakened two topic controls: Constella retrieval-model work and a
general agent tool-use study became unclassified. Version 3 added explicit
specific-topic precedence and restored both. In the final pass, all nine
positive controls retain their admission and topic; all three prior safe reject
candidates remain the same IDs: 70223, 73387 and 78251.

This deliberately selected, iteratively reused set is not a holdout or a corpus
accuracy sample. Cross-model agreement and quote presence are diagnostics,
not ground truth or proof of semantic entailment. Source clipping remains a
confounder for three cases; no numerical threshold was lowered to improve counts.

## Final disposition of the original 13 category cases

The following are diagnostic results under the new candidate. The original
80-record pilot artifact and all production rows remain unchanged.

| Saved example | Final JEV result | Confidence | DeepSeek reading |
| --- | --- | ---: | --- |
| Cosmos-H-Dreams | Models & Research | 0.96 | Same admission/topic |
| Gemini Robotics ER 2 | Models & Research | 0.86 | Same admission/topic |
| Gemini Robotics 2 | Models & Research | 0.98 | Same admission/topic |
| Applied-ML portfolio tutorial | AI Applications | 0.99 | Same admission/topic |
| Search-result/context representation | RAG & Data Systems | 0.86 | Same admission/topic |
| Cyber Risk Discourse | Security & Safety | 0.92 | Same admission/topic |
| Dify workflow triggers | Agent Frameworks | 0.81 | Same admission/topic |
| NIST risk-framework guide | Policy & Regulation | 0.83 | Same admission/topic |
| Groq/Bell commercial partnership | Business & Industry | 0.94 | Same admission/topic |
| Jesse Thaler appointment | non_ai; no topic | Not deletion-confirmed | Both models non_ai; deletion guards still preserve it |
| OlmoEarth embedding exports | Unclassified; raw AI Applications | 0.69 | Accepted, but reference proposed RAG; domain embeddings versus retrieval remains unresolved |
| NVIDIA Japan ecosystem overview | Unclassified; raw AI Applications | 0.58 | Reference non_editorial/Other; breadth, commercial framing and clipping remain relevant |
| Import AI mixed newsletter | Unclassified; raw Other | 0.74 | Both models accepted/Other; this is an intentional mixed-topic outcome |

Thus nine cases gain a confident topic with matching independent model readings;
one requires an admission correction rather than a forced topic, and three
remain unclassified. The newsletter's 0.74 confidence is confidence in Other,
not a failed named-topic confidence threshold.

Five final admission disagreements remain: NVIDIA's broad Japan overview,
Pixel Watch news, the Testsigma comparison, Walnut's buying-agent announcement
and the vibe-coded-app security article. Preserve them for boundary review.
Do not auto-delete them, decide correctness by majority vote or treat either
provider's confidence as a validated probability of factual correctness.

## Costs, artifacts and next step

| Provider | Original pilot + all clarification calls | Cumulative conservative usage-priced dollars |
| --- | ---: | ---: |
| JEV | 214 | $0.030643 |
| DeepSeek | 114 | $0.165654 |
| Total | 328 | $0.196297 |

Clarification/validation added $0.137353 to the original $0.058944 pilot.
The same SQLite journal and approval identity enforce provider and total caps
across all runs. There are no unknown-usage, inflight or failed calls; the five
known superseded original attempts retain their responses/costs. Completed
requests were not silently paid again. Amounts use conservative previously
checked rates and are not provider invoices. No additional money was approved
or topped up. Unused pilot headroom does not imply a mass-processing budget.

Private artifacts remain in `tmp/reenrich-2026-10-11`:
`rubric-clarification[-v2/-v3]-draft.json`, `rubric-validation[-v2/-v3]-plan.json`,
`-results.json`, `-reference.json`, `-report.json`, `-start-usage.json` and
`-usage.json`. The operational scripts are private ignored files under `tmp/`:
`run_rubric_validation.py`, `run_rubric_validation_v2.py`,
`run_rubric_validation_v3.py`. They reuse `pilot.lock` and
`pilot-journal.sqlite3`; no application/runtime code was changed for this stage.

| Final private artifact | SHA-256 |
| --- | --- |
| V3 draft | `36370cc44b041818c83c9af5dc59819c41bbf136813a8c735567523209557fcf` |
| V3 plan | `4f78ea155dadca5569827ad7b95681e8923d35bcd3ead4c3dea4f17db0405ecc` |
| V3 report | `b43a6071a96c208843a1a4f149d5445e5dfa249f10c7f0ecd72c2a30e5265e5b` |
| V3 results | `1607a7655ccda613ebac1d4fb9fdd198c48fd2cf5653942e91e99df3026d4990` |
| V3 reference | `5ce524d2ad2e2a8058746d64731e294843ac95757c166e038f86b0909b226282` |

Checks: frozen original plan/results/approval hashes unchanged; candidate choice
sets exactly preserved; IDs and complete responses checked; reference quotes
mapped to saved source; all three operational scripts passed scoped Ruff.
Full pytest/full `make lint` and production PostgreSQL restore/apply checks
were not run because this stage changed no application behaviour, committed
no code and applied no production data/schema changes.

Next: use clarification 3 as the candidate for a separately budgeted mass pass,
with the five admission disagreements and the two substantive unclassified
texts explicitly tracked. Keep the mixed newsletter unclassified. Reuse source
downloads, compatible assessments and summaries; new questions must not be
misrepresented as old cached decisions. The remaining 441 source/quality cases,
date repair, manifest, backup, PostgreSQL rehearsal and final production apply
remain separate required stages. Weekly stays off and retention stays unchanged.
