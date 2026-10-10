# Production legacy cleanup, 2026-10-11

Code: [implementation commit c787ce0](https://github.com/Orlv-85/AI_PARSER/commit/c787ce0f7ae9dbf0836899fa1b99db2eefc2e005).
Review: [PR #15](https://github.com/Orlv-85/AI_PARSER/pull/15).

The authorized one-time JEV cleanup completed successfully. Production articles
decreased from **8,549 to 7,430**. Exactly **1,119** frozen confirmed IDs were
deleted: 1,030 non-AI and 89 non-editorial. No changed or already-absent rows were
silently included; both counts were zero. No aliases needed deletion.

## Screening and budget

The consistent read-only snapshot was taken at **2026-10-10 22:24:30 UTC**
(October 11 in the operator timezone). It included all existing articles and
the complete dependency export, including admission and collection status.
The selection was independent of publication week, date, rank and old keyword
scores. No fresh crawling, DeepSeek, weekly or historical analytics ran.

| Result | Count |
| --- | ---: |
| Existing articles in snapshot | 8,549 |
| Current cached accepts, not sent again | 262 |
| JEV requests / checked articles | 8,287 |
| Newly checked AI editorial, kept | 3,487 |
| Total accepted, kept | 3,749 |
| Ambiguous/insufficient, kept | 3,681 |
| Confirmed rejects / deleted | 1,119 |
| Failed / unchecked | 0 / 0 |
| Changed rows skipped / already absent | 0 / 0 |

Model: `jev-1.13.0`. Admission policy: `semantic-admission-2026-10-10`.
Prompt: `semantic-admission-prompt-1`. Cleanup guardrails: `legacy-cleanup-1`.
The existing admission question and bounded title/summary/content were reused.
Destructive confidence was >= 0.95, with further relevance/body or deterministic
non-editorial corroboration. This is a conservative operating rule, not a
guarantee of correctness; ambiguous cases are retained.

Returned usage: **11,563,277 input tokens**, 1,397,363 output tokens. At the
[verified $0.042/M input rate](https://docs.typesafe.ai/models), usage implies
**$0.485657634**. The cumulative budget journal rounds each reservation upward
to microdollars and reports **$0.489843**, below the user limit of **$2**.
All requests returned usage; unknown usage is zero. No provider invoice amount
was returned. Successful responses and decisions are durable and resumable.

Examples of confirmed deletions include non-AI streaming/phone-shopping/sports
stories, `qdrant.tech/blog/page/...`, and corporate/landing pages such as
`leapwork.com/about/`, `octoperf.com/about/` and `kobiton.com/`.
AI releases, research and substantive guides are kept under the editorial policy.

## Manifest, restore and backups

Canonical normalized snapshot SHA-256:
`973d83e7a5538397d5f5393c6da2691e250118f461a1d692aa4f5cf1b49b85ad`.

Manifest SHA-256:
`7d8b2b861b8281e5de14ca9fa62582fa41363ee1efa7852f3b1aca65dd492864`.

Private server root: `/opt/ai-news/backups/legacy-jev-20261010T222433Z/`.
Original consistent export: `snapshot.json`. Full pre-apply PostgreSQL backup:
`pre-apply-postgres.sql.gz`, SHA-256
`11881c20c9663f0ee38348100191833c836e3208df762e5ce35cd0501eacb1e6`.

The retained operational directory is `operation/`; its `run/` contains the
normalized snapshot, complete manifest, response/usage SQLite journal, review
list, restore verification, targeted apply backup and applied ID list.
Targeted apply backup fingerprint:
`73e14c2ea37662d7ac8d7a6aad3e1467ae5b4741813f1c219563d76c1bc064c8`.
All server directories are private and data artifacts have mode 0600.
The operational code was run through a private import overlay, without replacing
the application image or changing its normal collector code.

The exact final manifest was rehearsed against the separate local PostgreSQL
database `legacy_cleanup_rehearsal` on port 55439. All 1,119 rows were deleted
and restored with exact exported table comparisons. A row inserted after the
snapshot survived targeted restore. Restore receipt and backup are retained in
`tmp/legacy-jev-cleanup-run/` locally and the private server operational directory.

Apply held the existing `/tmp/ai-news-auto-update.lock`, refused active collectors
and weekly workers, took the full backup, then locked dependent tables and checked
row/evidence/dependency hashes inside one transaction. Reject cache updates,
pending settlement, aliases and articles share that transaction.

## Retained references and future review

| Affected retained dependencies | Count |
| --- | ---: |
| Digest items / groups / reports | 60 / 11 / 6 |
| Legacy weekly items / reports | 2 / 2 |
| Weekly observations | 17 |
| Weekly jobs / snapshots / publications | 1 / 1 / 1 |
| Existing admission ledger references | 1 |
| Article aliases / weekly decisions | 0 / 0 |

Copied URLs, text, narrative, metrics and frozen report data remain in these
outputs. Reports were neither deleted nor regenerated. Structured and explicit
URL references are inventoried; unlinked prose mentions cannot be exhaustively
inferred. The full per-article dependency list is in the private manifest.

`review-unresolved.json` retains every one of the 3,681 ambiguous cases, with
ID, URL, title, evidence hash, original assessment/confidence, specific failed
guardrails, excerpt and dependencies. Full saved evidence and provider responses
remain available privately for a later policy pass.

| Review guardrail (may overlap) | Cases |
| --- | ---: |
| Short saved body/summary | 1,937 |
| Admission confidence below 0.95 | 1,745 |
| No deterministic non-editorial corroboration | 971 |
| JEV relevance above 0.05 | 622 |
| JEV insufficient evidence | 104 |

Revised deterministic cleanup rules can be tested against saved assessments
without model payment. Changed JEV questions/model need new versioned evaluation
of an explicitly selected set. A later deletion requires its own manifest,
current-row/dependency verification, backup and PostgreSQL restore rehearsal.

## Retention addition

At the user's explicit request, default retention is now **800 days** in CLI,
deploy, maintenance, sample configuration and operator documentation. Shell
commands prioritize an explicit environment override, then the server `.env`,
then 800. Both deployment workflows persist and pass `RETENTION_DAYS`; maintenance
also passes the repository override. The production `.env` and GitHub variable
were read back as `800`. Live server deploy/maintenance scripts were updated,
with prior scripts and `.env` backed up privately in `retention-800/`.

The size threshold stays **5 GiB**; target 4 GiB and seven-day tightening steps
are unchanged. At that threshold maintenance can still shorten retention.
The currently running image remains `v0.1.78`: the changed CLI default and workflow
code are delivered in the PR for the next release; normal live maintenance/deploy
already use the server override and updated scripts. Old-tag deployments must use
the updated workflow, which explicitly passes 800 even to an older script.

The prior `v0.1.78` deployment deleted 711 articles under the old 100-day retention;
698 had corresponding accept ledger entries with dates older than 100 days.
Their assessment payloads survived in the ledger. Increasing retention does not
retroactively restore those already deleted article rows. They were outside this
cleanup's existing-article set and were not re-evaluated or restored.

## Verification and code delivery

Production read-only verification found 1,119 deleted IDs absent, 1,119 ordinary
admission cache hits returning reject with no provider, and zero pending entries
for those canonical URLs. Health returned `{"status":"ok"}` and the public site
returned HTTP 200. Ordinary mandatory admission and JEV remain enabled;
weekly v2 remains false and active weekly cron entries remain zero.

Repo-wide validation: `make lint PYTHON=./venv1/bin/python` passed (Ruff, mypy,
pylint 10.00/10). Full pytest: **779 passed**, with isolated PostgreSQL enabled
and a separate file-backed SQLite database. Shell syntax and the standalone
cleanup script Ruff check also passed. Tests cover confidence/ambiguity, cache/resume,
budgets/provider failure, concurrent writers, FK ordering, atomic rollback,
idempotent apply/restore, preservation of post-snapshot rows and deployment
retention overrides. Exact final results and code/PR references accompany delivery.

See [operator documentation](legacy-articles-jev-cleanup.md). Private article
texts, full manifests, provider responses and backups are excluded from Git.
