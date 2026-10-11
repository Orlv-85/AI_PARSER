# Unpaid source download completed, 2026-10-11

Stage 1 is complete and paused before representative-sample/topic review.
Branch: `feat/reenrich-publication-dates-2026-10-11`.
No JEV, DeepSeek or Codex article-processing calls ran. Production articles,
admission, summaries, categories, dates, reports and runtime configuration were
not changed. The ordinary script downloaded and extracted source evidence;
Codex received aggregates only, not the corpus.

## Scope and results

The fresh repeatable-read, read-only snapshot included 7,430 articles and all
exported dependencies. All original 3,681 unresolved IDs still existed and had
unchanged canonical identities. Their current rows, evidence and dependencies
were frozen before downloading. The download process exited successfully with
no pending or started attempts remaining.

| Result | Count |
| --- | ---: |
| Frozen unresolved IDs / unique source URLs | 3,681 / 3,681 |
| Responses saved with HTML/text/date artifacts | 3,533 |
| Robots disallowed or unavailable | 135 |
| Network failures | 13 |
| Extracted pages passing initial deterministic quality checks | 3,240 |
| Unresolved quality/fetch cases, retained | 441 |
| JEV / DeepSeek / Codex article-processing calls | 0 / 0 / 0 |
| Model spend / new summaries / new categories | $0 / 0 / 0 |
| Production date changes / deleted articles | 0 / 0 |

`extracted` does not mean JEV accepted. The 441 unresolved cases include 293
saved responses with quality issues and 148 blocked/network-failed URLs.
Network failures were two ConnectError, seven ReadError and four ReadTimeout.
Quality flags overlap: 144 identity-unverified pages, 128 short/empty extracts,
96 paywall markers, 50 HTTP 403, 14 non-article redirects and smaller error groups.
These counts are conservative diagnostics, not deletion decisions.

## Publication evidence

Across the 3,533 saved responses, the extractor found 2,729 non-conflicting
publication metadata results, 37 conflicts and 767 without confirmed publication
metadata. The other 148 URLs have no downloaded article date evidence.
These are evidence counts, including quality-unresolved responses; they are
not dates applied to the database. Date-only precision, missing timezone,
modification dates and visible literal labels are preserved separately.

The offline audit of the other 3,749 existing articles found saved source
publication evidence for 651, no sufficient evidence for 3,093 and conflicts
for five. Thus 3,098 are currently date-only fetch candidates, subject to later
reconciliation and reuse of saved URLs. No additional date-only pages were
downloaded in this stage. Cleanup-created payload copies were excluded.
Original literal precision is unavailable for legacy normalized timestamps;
the audit explicitly records that limitation before any date application.

## Private artifacts and verification

Private local run: `tmp/reenrich-2026-10-11/`, approximately 3.43 GiB at completion.
Page directories contain `body.bin`, `page.html`, `text.txt`, `response.json`,
`evidence.json` and `attempt.json`. Robots files, snapshot, plan, original review,
fetch status, offline date audit and verification receipts remain private and
Git-ignored. Contents were not printed or committed.

Private server read-only snapshot:
`/opt/ai-news/backups/reenrich-20261010T232951Z/snapshot.json`.

Canonical normalized snapshot hash:
`bfa2d9330e06db140c462b4d09bf09627e2c21f266226e038215abf348a57971`.
Local snapshot file SHA-256:
`efd3416f445f9e119ee3d795a30e2efa73326290e3e988d633915f16ec99969e`.
Plan file SHA-256:
`cc10158945175783838d0cbdbc01b36339e922dfebe961936fde2ca04150e452`.

Offline cache verification passed for all 3,533 saved responses with zero errors:
response/evidence/HTML/text hashes, content-file permissions, frozen target
identities and public source/redirect URL checks. Artifact inventory hash:
`0c0e538bd91ac85323b9ce30d189c16b8cc55caaab42091ee3ce4320ef442c0e`.
No models ran during verification.

## Tooling and checks

The added [download script](../scripts/reenrich_articles.py) provides prepare,
fetch, status, verify and offline date-audit commands. The
[cache module](../src/app/storage/article_evidence_cache.py) implements private
durable attempts, no automatic refetch, bounded per-host pacing and quality
diagnostics. The [date extractor](../src/app/ingest/date_evidence.py) separates
publication/modification evidence and preserves unknowns/conflicts. Existing
ingestion/API/storage date semantics were not changed in this stage.
See [operator usage](article-source-cache.md).

Scoped validation passed: initial 65-test combined run covering the new cache
and script plus HTML/RSS regressions; subsequent four script tests including
offline integrity verification. Ruff passed for src/tests/the script; mypy passed
for src/tests; scoped pylint passed. Full `make lint`, full pytest and isolated
PostgreSQL apply/restore validation were not run: no commit/push, schema migration
or database application is part of this download stage. They remain required
before the corresponding later delivery/apply work.

## Next checkpoint

Select 50-100 diverse unresolved and previously accepted materials for bounded
source-based review. Agree primary topic criteria and UI behavior before paid
pilot or mass categorization. Comparison remains a separate material type;
compared products are a separate field. Batch-review taxonomy gaps rather than
interrupting the pass for each new subtopic. A new monetary budget is still
unset; optional sample summaries and all paid pilot/model work await that budget.
Unresolved download cases require separate conservative review, not automatic
deletion. The source cache is reusable for all later stages.
