# Re-enrichment applied to production, 2026-10-11

The user authorised mass processing, waived separate budget/stage approvals,
and authorised backup, PostgreSQL restore rehearsal and confirmed production
changes. The operation is complete. Existing downloads and compatible paid
responses were reused; disputed cases remain private for review.

## Applied results

| Result | Count |
| --- | ---: |
| Articles before / after | 7,430 / 5,963 |
| Updated article rows | 5,270 |
| Deleted confirmed rejects | 1,467 |
| Articles with supported summaries and enrichment | 406 |
| Comparison records | 90 |
| Changed publication timestamp values | 2,408 |
| Rows skipped for concurrent drift | 0 |

JEV assessed 3,238 of the original 3,681 records: 498 accepts, 1,467 confirmed
rejects and 1,716 unresolved records including source/input holds. DeepSeek
generated and checked summaries, with one narrow semantic repair for unsupported
claims. 408 summaries passed review; two admission-disputed records were held,
leaving 406 applied and 92 enrichment cases retained for review. Model review
and literal quote checks are safeguards, not proof of factual ground truth.

Publication status after application: 4,366 confirmed, 812 unknown, 92 conflicting
and 693 legacy unverified. Unknown/conflicting publication timestamps are NULL;
446 calendar dates retain unknown time/timezone, producing 1,350 NULL timestamps
in total. Legacy unverified values remain pending usable source proof.
The October 4 stored-publication count changed from 580 to 142. Discovery times
were not rewritten; removing rejects reduced that day's discovery count to 792.

The 3,098 additional date-only URLs were restricted to existing saved URLs lacking
sufficient proof: 3,036 completed, 60 blocked and two failed. Cached URLs were
reused. Source errors did not justify deletion.

## Safety and validation

- Full lint passed; full pytest: **824 passed, 9 skipped**. The skipped tests
  require optional `AINEWS_TEST_POSTGRES_URL` configuration.
- Separate full-data PostgreSQL 14 and PostgreSQL 18 rehearsals passed migration,
  transaction rollback, idempotent apply/restore, concurrent-edit refusal,
  changed-row skipping and exact restoration of every exported table. A new
  post-snapshot row survived targeted restore.
- Full production backup was restored in an isolated PostgreSQL 18 container
  with no exposed ports or production network. A fresh full backup and targeted
  rollback backup preceded production mutation; collector execution was locked.
- Post-apply checks matched every changed/deleted row to the backup's expected
  final state. Health, news, new-topic filtering, article detail and daily stats
  returned HTTP 200.
- Weekly and its cron remain off; admission and authentication remain enabled.
  Retention remains 800 days, size thresholds 5/4 GiB. No ordinary prune ran;
  confirmed date repair makes 69 rows eligible for future ordinary retention.
- Frozen reports were not rewritten; previous deleted/pruned articles were not
  restored. Legacy category values remain readable.

## Receipts and deployment

Production image: `ai-news-reenrich:20261011`, built locally on the unchanged
`ghcr.io/orlv-85/ai-parser:v0.1.79` base. Migration: `a42b750d0c44`. The collector
and compose configuration are pinned to the tested image. Source changes remain
uncommitted in the feature worktree; the next regular release must include them.

Manifest hash:
`3476a430fce0972d0f083158d84170528fd060de3b0e0d4854482eb78a1d3c00`.
Fresh full backup SHA-256:
`cada3d1f5693a84987645c0752f2801d352cbb969e4610c272b70a32bd08a4b1`.

Private server backups and receipts:
`/opt/ai-news/backups/reenrich-final-20261011/`.
Local cache, response/payment journal, held cases, manifest, backups and receipts:
`tmp/reenrich-2026-10-11/`. Operational scripts remain ignored under `tmp/`.

Cumulative conservative usage-priced spend, including pilot, clarification,
mass processing and summary checks/repairs: **$1.543343**; mass continuation added
$1.347046. This uses peak/cache-miss rates and is not a provider invoice.
Pricing was rechecked against [JEV](https://docs.typesafe.ai/models) and
[DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/).
All billing is known; no failed or inflight calls remain. A preserved sandbox
connection failure occurred before dispatch and has zero cost.
