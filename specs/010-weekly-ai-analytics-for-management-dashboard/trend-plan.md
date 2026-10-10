# Delivery plan: Weekly AI Analytics v2

Date: 2026-10-10
Status: Proposed; no application changes authorized by this planning document.
Specification: [trend-spec.md](trend-spec.md).

## Scope and delivery order

This extends feature 010. Preserve its original approved artifacts as historical
context. Implement in small slices after the proposed methodology is accepted.
Do not introduce Antigravity or rewrite the daily digest. Do not change source
registry schema, ingestion ranking, authentication, ports, or retention defaults.

### T01. Establish a reproducible baseline

- Inspect the affected production report using a supplied date or latest saved
  date; record input counts, writer path, stored sections, and available coverage.
- Add regression fixtures for the top-five cutoff, asymmetric old matching rules,
  multilingual titles, and duplicate copies.
- Inventory existing per-source logs for reliable coverage backfill; do not infer
  health from article absence. Record earliest verifiable historical day.
- Trace both `WeeklyAnalyticsRepo` and `build_feed_weekly_payload` callers before
  selecting the shared service interface.

### T02. Persist coverage and evidence identity

- Add migrations and repositories for publisher grouping/versioning, per-source
  daily coverage, article publication provenance, event observations, topics,
  assignments, and immutable analytics snapshots/revisions.
- Persist existing pipeline source outcomes independently of optional log emission.
  Record expected attempts, successful empty/304 results, failures, and truncation.
- Keep alias publication time unknown unless recoverable from evidence.
- Introduce validated checked-in topic definitions without editing `sources.yaml`.
- Test migrations and round trips on SQLite and PostgreSQL.

### T03. Build the shared pure trend calculator first

- Proposed module: `src/app/core/weekly_analytics.py`; keep storage and provider
  I/O outside its arithmetic functions. Existing repo methods become adapters.
- Implement windows, cohort/quality gates, publisher-balanced proportions,
  support thresholds, New history, stable/resurfacing states, and deterministic sort.
- Test AC-01 through AC-13 and AC-16/19/20/22 using synthetic assignments with
  no provider calls. Verify edge boundaries and null growth at zero baseline.
- Test source-balanced arithmetic using unequal publisher volumes as well as
  equal-volume examples, and ensure unresolved items remain in denominators.

### T04. Add cached JEV enrichment and bounded DeepSeek assistance

- Proposed module: `src/app/core/weekly_enrichment.py`.
- Follow existing clients in `src/app/core/jev.py`, `source_review.py`, and
  `scripts/digest_generator.py`; extract only the shared transport needed here.
- Reuse `JEV_API_KEY`, `AINEWS_JEV_*`, and `DS_API_KEY`; add separate weekly model,
  prompt/version, timeout, token, and job-budget settings.
- Implement topic assignment, uncertain-case resolution, bounded event matching,
  and proposed-topic historical reassignment. Do not change ingestion scores.
- Test provider contracts with mocked HTTP, invalid probabilities, unknown IDs,
  empty/truncated JSON, timeouts, budget resumption, and poisoned article text.
- Reuse cached classification and frozen outputs on retries and report replay.

### T05. Add narrative with evidence validation

- Proposed module: `src/app/core/weekly_narrative.py`.
- Freeze metrics before constructing prompts. Resolve evidence references to
  stored URLs server-side; validate claim support and numeric consistency.
- Implement deterministic narrative templates and AC-14/15.
- Check narrative length against current storage/API limits.

### T06. Unify job and publication behavior

- Add a durable job/revision repository and worker command using existing CLI
  conventions. Lock or lease by date, methodology version, and input fingerprint.
- Replace the two independent legacy calculation paths behind a v2 feature flag.
  Keep existing command names/flags as adapters, documenting v2 limit semantics.
- Route `scripts/run_weekly_analytics_job.sh` through the worker. Monday pipeline
  publication records a job and returns; it must not call providers inline.
- Preserve legacy manual POST payloads but block silent overwrite of verified v2.
- Ensure GET reads snapshots without external calls. Implement AC-17/18/22.
- Inspect deployment scheduling before changing scripts; preserve cadence by
  default. Document how initial backfill is drained and failed jobs are retried.

### T07. Expose metrics and meaningful empty states

- Add weekly-specific optional models in `src/app/web/models.py`; update report
  hydration and `src/app/web/app.py` serializers without changing daily types.
- Update both `weekly_analytics.html` and `digest.html` preview.
- Add evidence details, periods, coverage, share/count metrics, and quality reason.
- Keep legacy archive pages usable and identify old methodology explicitly.
- Test AC-20/21, optional-field compatibility, no-data/partial-data rendering,
  links restricted to stored HTTP(S) URLs, and escaped source/model text.

### T08. Calibrate, backfill, and roll out

- Run the semantic and eight-week replay evaluations described in the spec.
  Freeze thresholds after tuning; use separate weeks for final evaluation.
- Produce a short comparison artifact with prior/v2 section counts, reasons for
  differences, evidence examples, quality exclusions, latency, and model usage.
- If historical coverage cannot be proven, enable data collection first and mark
  previews unverified until sufficient observed history exists.
- Publish v2 behind a feature flag. Backfill saved reports explicitly into new
  revisions; do not silently mutate legacy history or discard old snapshots.
- Rollback switches new publication to the previous method while retaining
  additive data and revisions. No destructive rollback migration is required.

## Validation matrix

| Area | Existing regression surface | New checks |
|---|---|---|
| Pure metrics | `tests/unit/test_news_digest_repo.py` | New trend calculator tests, AC-01..13/16/19/20/22 |
| Providers | `tests/unit/test_jev.py`, `test_deepseek_digest.py` | Weekly enrichment/narrative mock tests, AC-14/15 |
| Job adapters | `tests/unit/test_digest_generator.py` | Complete input, leases, cache, revisions, AC-17/18 |
| Public API/UI | `tests/unit/test_web_weekly_analytics.py` | Optional metrics, old request shape, both empty states |
| Storage | Existing storage/migration tests | SQLite and PostgreSQL additive migrations and replay |

For each implementation slice run the smallest relevant tests first. Final
pre-commit/push gates remain:

```sh
rtk proxy make lint PYTHON=./venv1/bin/python
rtk proxy ./venv1/bin/pytest
```

If job scripts change, also run the repository shell syntax checks. Live provider
evaluation is separate from unit tests and needs configured keys and an explicit
recorded usage budget. This document does not claim those checks have run.

## Dependencies and product decisions

- Start with the proposed thresholds; release values depend on recorded evaluation.
- Keep the existing English UI; localized copy is a separate task.
- Initial scope is topic attention, not sentiment, market demand, or every new
  product announcement. Stable/resurfacing signals are inspectable separately.
- Semantic deduplication, topic taxonomy, and publisher ownership have uncertainty;
  persist evidence and overrides so corrections produce auditable new revisions.
- Durable historical coverage is a release dependency, especially for truthful
  Down and New. It cannot be manufactured from a richer prompt.
