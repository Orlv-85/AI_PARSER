# Weekly report 2026-10-11: completed stage 3

**Stage 3 is complete. The English candidate is calculated and verified, ready
for the provider-free publication workflow in stage 4.** Its honest product
status is `insufficient_data`: observed facts and sources are available, but
New/Up/Down cannot be confirmed. No production publication, merge, deployment,
scheduler or v2 flag change occurred.

The initial failed-run history is preserved in
[the checkpoint before recovery](weekly-stage-3-checkpoint-before-recovery-2026-10-11.md).
The user's subsequent authorization allowed the recovery repair and continuation
in this session; financial reconciliation was not required.

## Candidate, code and provenance

Working checkout: `/private/tmp/ai-parser-weekly-stage2-20261012`.
Recovery implementation:
[`18b49a7e5c6d9f3143166568e9cce01e8a7ed36a`](https://github.com/Orlv-85/AI_PARSER/commit/18b49a7e5c6d9f3143166568e9cce01e8a7ed36a),
pushed to [PR #23](https://github.com/Orlv-85/AI_PARSER/pull/23), open and unmerged.
Final documentation may have a later HEAD; all ten frozen calculation code hashes
identify this implementation and were verified after generation.

Current private root:
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r4`.

- Candidate: `candidate.json`, SHA256
  `750be9c70ceffb88890c5557fd651c609451a344ddb7800a35fd936c74aac7ba`.
- Frozen identity / snapshot ID:
  `eab060734f7089b5270df1e32c709fa065be53c317453fe749ca5c3f7ebf717c`.
- Frozen file SHA256:
  `e05ba25486b9a54b07864075525ff603197d07242621412262fdbb6e759e2709`.
- A readable private English preview is `candidate-preview.md`; it is derived
  from the verified payload's own summaries, counts and evidence URLs.
- The isolated candidate database contains revision 1. No target production
  revision has been created.

All five input byte hashes and receipt references remain identical to
[the stage 1 hash map](weekly-stage-1-hashes-2026-10-11.json).
Manifest v4 SHA256 is
`c9bea6115329a605bb809540d8b591d1975b4268d9e0251ec4929952cb4b033b`;
snapshot SHA256 is
`9c7f73cde3136a5cc3425e0447adf42b1accae7a63d30706722f8b40a8e5fc00`.
No production export or old pilot was repeated.

## Full scope and denominators

All 932 assigned Articles remain in the payload. Calendar precision is retained
for all 123 calendar inputs; no synthetic UTC instants or support days were added.
The 2,350 unassigned dates, 26 ambiguous boundaries and 2,685 outside-scope Articles
remain in accounting: **932 + 2,350 + 26 + 2,685 = 5,993**.

Final admission: **694 compatible accepted / 237 model-rejected / 1 unresolved**.
Topic assignment resolves 424 Articles. The unresolved admission is eligible and
retained in the denominator. Accepted admission is not overridden by negative
topic relevance. Rejected Article records remain in the frozen assignments for
provenance and do not contribute eligible observations.

There are 695 eligible Article inputs and 694 counted event-publisher-week
observations after one exact duplicate collapse. Of these, 423 have resolved
topics and 271 remain unresolved. All unresolved observations stay in the observed
denominators. No publisher qualifies for the comparable cohort: its statistics
are zero because the cohort is absent, not because observed news is absent.

| Window | Frozen Articles | Counted observed event-publisher observations | Unresolved topics in denominator |
| --- | ---: | ---: | ---: |
| W0, Oct 5–11 | 266 | 171 | 61 |
| W1, Sep 28–Oct 4 | 158 | 130 | 48 |
| H2, Sep 21–27 | 95 | 75 | 32 |
| H3, Sep 14–20 | 199 | 150 | 58 |
| H4, Sep 7–13 | 214 | 168 | 72 |
| Total | **932** | **694** | **271** |

Semantic matching remains incomplete: 108 unknown-UTC-time cases, 69 ambiguous
pairs and 15 candidate-limit cases are recorded. These are case counts, not
disjoint Article exclusions. JEV made 1,402 same-event decisions. Counts remain
observed event groups, rather than independently certified distinct occurrences.

## Topics, English explanations and limits

There are **25 topics, all `insufficient_evidence`**, retained in `other_signals`.
New / Trending Up / Trending Down each contain zero confirmed cards. No thresholds
were changed. Share, growth and percentage-point changes are null for every topic.

Examples of observed facts, with the previous week shown first:

| Topic | Previous event groups | Current event groups | Current publisher groups |
| --- | ---: | ---: | ---: |
| Agent tooling | 10 | 15 | 7 |
| Language models | 10 | 13 | 4 |
| Enterprise agents | 6 | 12 | 6 |
| AI robotics | 0 | 9 | 7 |
| Open-weight models | 3 | 7 | 6 |

These differences do not establish growth or novelty. Publisher counts measure
publisher groups, not independent original reporting. Coverage is unknown and
complete New history is unproved. Overall reason is `input_incomplete` because
semantic/event matching is incomplete; `coverage_reason=coverage_unknown`
separately preserves the historical coverage limitation. Retrieval scope is full.

Narrative mode is **template**. All 25 English explanations are generated from
verified arithmetic and explicitly leave growth/decline/novelty unconfirmed.
For the eight selected narrative candidates, four packets exceeded the frozen
input cap, one completion was truncated and three returned empty claim lists.
The existing fallback contract handled these cases. No unsupported DeepSeek
claims or interpretations were retained; zero factual model claims require
publication support approval. The read-only narrative review reproduced the
fallback reasons without further provider calls or exposing source text.

The frozen generation cutoff and all original evidence identities, titles,
publication precision, event/publisher IDs and stored URLs were preserved.
Evidence selection and every topic's counts were reproduced from assignments.
Mixed calendar evidence prevents a precise first-observed timestamp.
No semantic precision certification or complete coverage reconstruction is claimed.

## Recovery and validation

A private backup of the parent root's two SQLite files and metadata is retained
under `tmp/weekly-stage3-20261011-manifest-v4-r3-backup-before-recovery`.
Parent identity:
`614fcdd4c8e81d19686452b653e9e9b478d5e1e089f8ba88e7d235de73eea790`.
Its frozen file, database bytes and successful responses remain unchanged.

The new revision copied the full journal/cache, retaining all 346 parent attempts,
including 345 successful responses. Its lineage records the parent hashes.
The original ReadError is reviewed with its full conservative commitment and
unknown actual usage. A linked second attempt succeeded. There were no further
transport failures. Ordinary run limits were resumed on the same r4 root; the job
completed at attempt 5. A subsequent completed run returned the identical candidate
hash with zero additional dispatches.

The repair permits at most two attempts per request under an explicit frozen
transport-review policy. Both attempts remain accounted for. Exhausted requests
become unresolved and allow other tasks to continue. Unreviewed failures, missing
usage, inflight/concurrent dispatch and cumulative monetary caps still block.

Validation completed:

- Scoped provider/recovery/frozen runner tests: 45 passed.
- Final repo-wide `make lint PYTHON=./venv1/bin/python`: passed (ruff/mypy/pylint).
- Final repo-wide pytest: **875 passed, zero skips**, with isolated SQLite and a
  UTF-8 PostgreSQL 14 private socket. The test cluster was stopped afterward.
- GitHub recovery-commit CI: lint and tests passed.
- Private candidate verification: five input hashes, all ten code hashes, lineage,
  complete scope, unchanged source fields, dates, rejects/unresolved accounting,
  independent deduplicated denominator count, pure-calculator replay of every
  metric/state/evidence item, contract schema, null unavailable metrics and
  English template arithmetic passed.
- Read-only narrative validation and parent response byte comparisons passed.
  Validation made zero provider calls. Completed-run idempotence was verified.

Journal total: **$0.501931 committed**, including **$0.005059 unknown reserve**
($0.496872 known usage-priced peak; not an invoice); cumulative caps remain
$10 total / $7 JEV / $3 DeepSeek.

| Provider | Attempts | Successful responses | Known input tokens | Known output tokens | Unknown-usage attempts |
| --- | ---: | ---: | ---: | ---: | ---: |
| JEV | 3,230 | 3,230 | 5,733,847 | 268,452 | 0 |
| DeepSeek | 337 | 336 | 645,205 | 50,611 | 1 |

Two verified positive assignment imports were reused. The old 154 conditional
keys were not imported wholesale. All successful responses and compatible decisions
were reused across resumes; the linked transport retry is a separate retained
attempt. `quality.provider_calls` is per invocation and `provider_tokens` is empty
in this journal adapter; `quality.durable_provider_usage` and `usage.json` are the
authoritative cumulative records.

## Private receipts and stage 4

Files are private under a mode-0700 root; payloads/databases/receipts are mode 0600.
Corpus, provider responses and credentials remain outside Git and public docs.

| Artifact | SHA256 |
| --- | --- |
| journal.sqlite3 | `4b584c4b8d5b7778db2dadfdf3c9db3706032c0864aa512a5e79350676eaf7c5` |
| weekly.sqlite | `7c3ab3f1404613a79b7bae461d5fe5425f58cbc41888b569fe623b020101c7c2` |
| usage.json | `fcadaf116a8ffd0e7c26a45ccd4c6e492903ab669f84bf25b8ccf1292e84d2a9` |
| candidate-verification.json | `3d27fb887a7e7a6584a779f58053cbf81ffd5a234ff3ddb053a54f3b5ff00ff2` |
| narrative-review.json | `726ee3ac64450b5e9ae445856407d395cb7a3a931b734a61efd5952a697aca51` |
| recovery-receipt.json | `646f14b7dcd7d369d6b1c6874f187b7cb2b998d5a155b5296c014febadd27dea` |
| candidate-preview.md | `e5a325cef49c9bb6f0a1024b8a9babcb5658f88b7479b1ce1fb496a685996740` |

Stage 4 must use **r4**, not the superseded r3 root. With the reviewed code deployed,
normal target migration, backup and target URL supplied through an environment
variable (never print it), the provider-free import is:

```sh
rtk proxy env PYTHONPATH=src ./venv1/bin/python scripts/weekly_frozen_report.py publish \
  --root /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/tmp/weekly-stage3-20261011-manifest-v4-r4 \
  --candidate-sha256 750be9c70ceffb88890c5557fd651c609451a344ddb7800a35fd936c74aac7ba \
  --database-url-env WEEKLY_TARGET_DATABASE_URL --approve-publication
```

Use [the existing stage 4 prompt](prompt-weekly-stage-4-publish-2026-10-12.md)
with this result. No further model analysis is required to publish this candidate.
Merge/release, target-state checks, production backup/import, API/UI verification
and daily preservation belong to stage 4. The general weekly scheduler remains off.

User preferences persist in private `session-context-recovery.json`: focus on the
result without preliminary economic discussions; preserve automatic accounting;
save every future session prompt in a docs file before delivery and link it.
Global pytest-only permissions and a launcher for arbitrary interpreter/env options
were installed in `~/.codex/rules/pytest.rules` and `~/.codex/bin/run-pytest`, with
the preference recorded in `~/.codex/AGENTS.md`.
