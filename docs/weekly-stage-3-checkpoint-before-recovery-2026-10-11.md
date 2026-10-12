# Weekly report 2026-10-11: stage 3 checkpoint

**Stage 3 is incomplete. No publishable candidate exists.** The authorized frozen
calculation ran once and stopped on a DeepSeek transport failure, rather than a
budget limit. No publication, merge, deployment, scheduler or feature-flag changes
were made. Application code, immutable input and provider journals were not edited.

## Provenance and validation

Checkout: `/private/tmp/ai-parser-weekly-stage2-20261012`.
Implementation: `8743fb00f39c3a4df9f7b1afbbff2253cf790405`, PR #23.
Checkout HEAD: `dff73d338fcb177b799a2f438896d061351c8745`; the differences from
the implementation commit are documentation only. All ten frozen module hashes
were checked before dispatch and again after the stopped run.

Private input root:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage1-20261011`.
All five byte hashes and the receipt's internal references were verified before
dispatch. They match [the stage 1 map](weekly-stage-1-hashes-2026-10-11.json):

| Input | SHA256 |
| --- | --- |
| snapshot.json | `9c7f73cde3136a5cc3425e0447adf42b1accae7a63d30706722f8b40a8e5fc00` |
| selection-manifest-v4.json | `c9bea6115329a605bb809540d8b591d1975b4268d9e0251ec4929952cb4b033b` |
| source-evidence.json | `4f5ae0b18e7e3d59bfbf23303496b5f401ffaa611073ba8737b14b6660188208` |
| published-target.json | `12a7772b0db49842906ab15c189a8baeb4eceedd067a4efbea9de0ae5a948a43` |
| handoff-receipt.json | `ec22e8f4bb0e74aa14d74eb6cc43a22275b0534e80c8f1b1cd910d45787ab697` |

Current private run root:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r3`.
Frozen identity:
`614fcdd4c8e81d19686452b653e9e9b478d5e1e089f8ba88e7d235de73eea790`.
Frozen file SHA256:
`48dfa16f9a0f7b2f42fbaa982d0ee8a8d7dc3b47be8fccfa0ed6bc54041f466b`.
Journal identity was verified with its own spaced-JSON fingerprint convention.
The earlier zero-call preparations were not used.

All 932 week-assigned Articles remain in scope: W0/W1/H2/H3/H4
266/158/95/199/214. Accounting retains 2,350 unassigned dates, 26 ambiguous
boundaries and 2,685 outside-scope Articles, totaling 5,993. All 123 calendar
inputs retain uncertain UTC publication time. Initial compatible admission is
110 Articles; 822 require fresh admission. Two full-key positive assignments
were imported; the old 154 conditional keys were not imported wholesale.

Both SQLite databases passed `PRAGMA integrity_check`. Job status is `retry`,
attempts 1, error `provider_outage_unknown_billing`, with its lease released.
There are zero saved snapshots and no `candidate.json`. A read-only reserve
probe confirmed that further dispatch stops with
`unknown_or_failed_previous_call_requires_review`, without changing the journal.
Private verification scripts and aggregate receipts are retained in the run root.
Full lint/pytest were not run: no application code changes or commit/push occurred.
Final payload arithmetic, evidence, topic states, English explanations and
claim-support validation cannot be reported as passed without a candidate.

## Prices, budget and usage

Before dispatch, official prices were checked against the frozen constants:
JEV $0.042 per million input tokens and free output
([TypeSafe, October 7](https://typesafe.ai/blog/jack-jill-jev-case-study));
DeepSeek Flash peak $0.30 input / $1.20 output per million tokens
([official pricing](https://api-docs.deepseek.com/quick_start/pricing/)).
No discount was assumed. The conservative admission/assignment reservation
estimate was approximately $4.71 before event/support work. Cumulative caps
remain $10 total / $7 JEV / $3 DeepSeek.

| Provider | Dispatched | Complete responses | Unknown usage | Input tokens | Output tokens | Usage-priced peak USD | Committed USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| JEV | 292 | 292 | 0 | 701,452 | 38,096 | 0.029603 | 0.029603 |
| DeepSeek | 54 | 53 | 1 | 101,407 | 7,710 | 0.039698 | 0.044757 |
| Total | 346 | 345 | 1 | 802,859 | 45,806 | 0.069301 | **0.074360** |

These are conservative journal amounts, not an invoice. Known token counts exclude
the failed request. DeepSeek cache-hit tokens are zero; known total tokens are
109,117. No successful paid dispatch was repeated. Failed-request commitment
of **$0.005059** is retained in full.

Initial CLI attempts stopped before any dispatch because local auth configuration
failed Settings validation. The successful invocation used `PYTHONPATH=src`,
the prescribed env file and temporary process-local auth fields; no env file or
production auth setting was changed. The runner creates only its isolated
candidate SQLite database.

## Failure review and remaining scope

At **2026-10-12 12:01:55 UTC**, one DeepSeek ambiguity request failed with
`httpx.ReadError`. There is no HTTP response, provider payload, usage or received
timestamp. This identifies a network-read failure; the journal does not retain
the underlying exception message or cause, so provider, proxy and local-network
causes cannot be distinguished. This was not a budget stop or an HTTP rejection.

The user subsequently accepted the uncertain expense and removed invoice
reconciliation as a prerequisite for continuation. That instruction is preserved
in private `billing-review.json`. Keep the full reservation in cumulative expense;
actual usage remains unknown. Do not ask again for financial acceptance of this
same failure. Frozen caps still apply. The failed item remains semantically
unresolved; no negative decision was fabricated.

There is a remaining recovery gap in the frozen runner: `reserve()` blocks failed
or unknown-usage entries, and `call()` rejects a saved entry unless it is a complete
response with known usage. It has no general reviewed transport-failure recovery
method. Existing pilot summary-review methods do not apply to this case. Merely
rerunning the command or labeling the row reviewed cannot safely resume it.
Return this gap to stage 2 as required by the frozen-run instructions; do not
silently patch calculation code, alter frozen identity or clear accounting.

Cache contains 129 admission keys (94 accepted, 25 non-AI, 10 non-editorial),
53 ambiguity keys, 77 assignment keys and 163 JEV keys. Assignment keys include
the two imports; 70 have positive assignments and seven negative relevance
results. Negative topic relevance does not override accepted source admission.

A provider-free, read-only replay over all 932 Articles finds 205 with compatible
admission, 36 rejected and 691 still requiring admission dispatch/review. Among
the 205 admitted Articles, 71 have resolved assignments, 41 remain unresolved
from available responses/validation and 93 require further dispatch/review.
Key counts differ from Article counts because exact decisions may serve duplicate
inputs. These are checkpoint counts, not final report denominators or topic states.
The failed ambiguity request is linked privately to its Article and exact key.

Comparable publisher cohort and full New history remain unproved. Thresholds,
dates and semantic responsibilities are unchanged. No completed event clustering,
metric calculation or narratives are claimed. Publication stage 4 must wait.

## Preserved checkpoint hashes

All files below are in the current private root, mode 0600 under directory 0700.
No corpus, provider responses or credentials are copied to public documentation.

| Artifact | SHA256 |
| --- | --- |
| journal.sqlite3 | `8e47bcd2e1ee18457b370133e0f2ce96458ddaaf319c635bcd61f0d576380c83` |
| weekly.sqlite | `a9fc3697a755b036e00cebc7e4d9d6e847edd8bf353b726f7f4c760f8eccfd86` |
| usage.json | `4d8c8a07fd271aabb1cc0de7f2dcf3ba1d52064a2083c9f7aed9ccd66bf4e489` |
| stage3-verification.json | `7cc247387ac60f589506ecc02d9dca565affdb43bab3cdfce5e39f10a237e9f4` |
| checkpoint-review.json | `03c233bbddd8bee8c8cdc402106135dcc36ede14901e4a23be54f63bd2812616` |
| billing-review.json | `5bbf8ca2ca6d0a18afb8a8368b3209538115b2236bee550578bf7e46e5bc2e49` |

Next session: [repair recovery in stage 2](prompt-weekly-stage-2-recover-reviewed-failure-2026-10-12.md).
Every future session/handoff prompt must first be saved in a descriptive docs file,
preserving earlier prompts and providing a clickable link. The existing stage 4
prompt remains historical guidance, not authorization to publish this checkpoint.
