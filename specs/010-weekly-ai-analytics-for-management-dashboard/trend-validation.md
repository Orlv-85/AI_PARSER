# Weekly attention v2 delivery and validation

Implementation authorized by the user on 2026-10-10. Delivery branch:
`feat/weekly-analytics-v2-trends`. V2 remains disabled by default.

## Baseline

Read-only production inspection on 2026-10-10 found the latest stored report dated
2026-10-09, created at 2026-10-10T08:37:59.678735Z. Its summary reports 230 current
stories, a +165 difference, 225 New, zero Up and 60 Down. These are the legacy
report's declared input/candidate counts, not verified event counts. The current
code has two writers: `WeeklyAnalyticsRepo` (top-five database selection) and
`digest_generator.py::publish_feed_weekly` (HTTP feed selection). The scheduled
runner invokes the latter; Monday ingestion invokes the former. Production writer
identity and complete historical input could not be proved from the public API.

Local available logs were orchestration/source-repair artifacts, not a complete
timestamped per-source scheduled coverage ledger. No earliest verifiable historical
coverage day is established. Aggregate FetchRun and Source timestamps are not
treated as a backfill of source health. Prospective collection is required unless
an operator supplies a complete trustworthy ledger.

## Implemented slices

- Additive source configuration, collection outcomes, publication provenance,
  topic definitions, semantic decision caches, frozen jobs and immutable revisions.
- Pure complete-input, equal-publisher arithmetic with UTC windows, support,
  completeness, retention, novelty and deterministic ordering gates.
- Separate JEV topic/event decisions, constrained DeepSeek ambiguity and emerging
  topic proposals, full 35-day reclassification after taxonomy changes, validated
  narratives and deterministic fallback. Failed/ambiguous cases remain inspectable.
- A shared durable worker, unique input keys, leases, budget resumption, atomic
  revision publication, freshness preservation and legacy overwrite protection.
- Weekly-specific optional API fields, evidence and quality on the report page,
  meaningful empty states on both pages, and a provider-free GET path in v2.
- A read-only eight-week audit export with all topic metrics, legacy comparisons,
  stratified assignment review samples, event pairs and recorded model usage.

Controlled acceptance fixtures cover direction, volume versus share, healthy-zero
decline, failed coverage, multilingual identity, exact/event duplicates, syndication,
novelty/history/resurfacing, low support, new publishers, complete reads beyond 200,
provider rejection/fallback, frozen input/cache reuse, leases/revisions, taxonomy
replay, UTC boundaries, empty states and deterministic evidence/ordering. The audit
does not label unreviewed samples as accurate or automatically certify a release.

## Verification

- Full `make lint PYTHON=./venv1/bin/python`: passed (ruff, mypy, pylint).
- Full pytest with an isolated local PostgreSQL instance: 645 passed, no skips.
  PostgreSQL was available through Homebrew; a temporary cluster listened only on
  its private Unix socket and was stopped after tests. SQLite migration/round-trip
  tests and PostgreSQL migration/lease/snapshot round-trip tests both ran.
- Shell syntax: every script in `scripts/*.sh` and the orchestration shell skill
  directory passed `bash -n` individually.
- JavaScript extracted from weekly_analytics.html and digest.html passed
  `node --check`. API tests verify snapshot hydration, no-data compatibility and
  HTTP 409 for legacy overwrite attempts.
- CLI help verified for `weekly-analytics` and `weekly-analytics-audit`.

No live paid provider evaluations or production writes were performed. Unit/mock
checks establish code behavior, not semantic precision on real news.

## Release dependency

An eight-week real replay and manual review of 200 assignments/50 event pairs have
not run: trustworthy historical coverage is unavailable and no live usage budget
was recorded. Collect coverage first, review topic definitions and publisher
ownership, then export/review the replay using separate tuning and evaluation
weeks. Record accepted/unresolved rates, false positives, missed supported signals,
section counts, evidence, latency and model usage before enabling publication.

Two complete observed weeks can establish Up/Down; New needs 35 observed days and
its stricter historical cohort. Unknown publication dates and uncertain event
matches can suppress confirmation conservatively. Empty sections are a quality
result with an explicit reason, not a quota failure. Existing reports remain legacy
and explicit backfills create new revisions. Rollback retains additive evidence.
