# Plan: storage layout and feature docs (2026-10-21)

Status: proposal, no moves yet. Written after the shared helpers were moved out of feature files
(`storage/journal_files.py`, `core/provider_costs.py`) and the one-off `storage/reenrich_apply.py`
was removed (same PR).

## Flat or mirror `core/`?

Recommendation: **stay flat for now; group only the one-off cleanup modules** when their feature
is next touched.

- `core/` has packages (`ingestion/`, `daily/`, `weekly/`, `sources/`) because each package holds
  several modules of one feature. In `storage/` most features have one module (`admission.py`,
  `digest_repo.py`, `source_repo.py`); a package per module adds import churn and no locality.
- The only group with several modules and one purpose is the finished cleanups
  (`legacy_cleanup.py`, `cleanup_journal.py`, `non_news_cleanup.py`). A `storage/cleanup/` package
  would make "finished one-off, do not build on" visible. Not worth a separate PR; do it with the
  next change of one of them, or when deciding to delete them.
- `daily_signals*.py` already share a prefix and one doc (`core/daily/signals.md` covers
  `storage/daily_signals*.py`); a `storage/daily/` package would only rename paths in that doc.
- Weekly v2 is deferred (see below), so `storage/weekly.py` and `repos.py` stay where they are.

## Modules

| Module | Feature | Doc that should cover it | Recommendation |
| --- | --- | --- | --- |
| `__init__.py`, `db.py` | engine, sessions, re-exports | none (infrastructure) | keep; no doc needed |
| `models_sql.py` | all tables | each feature doc names its tables | keep flat |
| `migrations/` | schema versions | per feature (`signals.md` already globs `*daily_signal*`) | keep |
| `journal_files.py` | canonical JSON, fingerprint, private atomic writes (shared) | none; pinned by `test_journal_files.py` | keep; shared helper, not a feature |
| `admission.py` | collection status, admission decision cache | `core/ingestion/pipeline.md` (already in `covers:`) | keep |
| `article_repo.py` | articles: queries, stats, retention | `core/ingestion/pipeline.md` for writes; reading side has no doc | add to `pipeline.md` `covers:` when next changed |
| `source_repo.py` | sources registry | `core/ingestion/pipeline.md` | add to `covers:` when next changed |
| `source_candidate_repo.py` | source onboarding candidates | future `core/sources/onboarding.md` | doc when onboarding is next changed |
| `digest_repo.py` | daily digest reports | future `core/daily/enrichment.md` | doc with daily enrichment |
| `daily_signals.py`, `daily_signals_ledger.py` | Daily AI Signals | `core/daily/signals.md` (already in `covers:`) | keep |
| `reenrich_pilot_journal.py` | paid provider journal (budget caps, reservations, recovery); used by daily enrichment, daily admission (`core/jev.py`), weekly frozen | future `core/daily/enrichment.md` | live, misnamed: rename to e.g. `provider_journal.py` with the daily enrichment doc (weekly `code_hashes` names the path, see below) |
| `article_evidence_cache.py` | private source-page cache; used by daily enrichment and the re-enrichment scripts | future `core/daily/enrichment.md` | live; cover it in that doc |
| `legacy_cleanup.py` | one-off legacy cleanup (manifest, apply, restore); ran 2026-10-11 | none; operator guide `docs/legacy-articles-jev-cleanup.md` | finished one-off; still holds `known_article_fk`, which CI uses to guard new FKs to `articles` (`tests/integration/test_legacy_cleanup_postgres.py`) |
| `cleanup_journal.py` | provider journal of the legacy cleanup run | none | finished one-off, only `scripts/legacy_articles_cleanup.py` uses it |
| `non_news_cleanup.py` | read-only non-news cleanup plan and backups; plan made 2026-10-10 | none; record `docs/archive/2026-10-10-12/non-news-cleanup-2026-10-10.md` | finished one-off; `EXPORT_TABLES` and `_reference_ids` are imported by `legacy_cleanup.py` |
| `repos.py` | weekly analytics repo (`WeeklyAnalyticsRepo`) | none | weekly v2, deferred |
| `weekly.py` | weekly v2 evidence ledger and jobs | none | weekly v2, deferred |

## Features without a code doc

| Feature | Live or finished | Recommendation |
| --- | --- | --- |
| Daily digest enrichment (`core/daily/enrichment.py`, `reenrich_pilot.py`, provider journal, page cache, `digest_repo.py`) | live (`publish_day`; see `docs/troubleshooting.md`) | write `core/daily/enrichment.md` next time it changes; rename the "pilot" modules then |
| Re-enrichment of existing articles (`scripts/reenrich_articles.py`, `scripts/reenrich_pilot.py`) | finished 2026-10-11 (`docs/archive/2026-10/reenrich-production-results-2026-10-11.md`); the scripts remain as tools | no code doc; `docs/article-reenrichment.md` stays the operator record; decide delete-or-keep of the two scripts separately |
| Legacy cleanup (`legacy_cleanup.py`, `cleanup_journal.py`, script) | finished 2026-10-11 | no code doc; before any deletion, move `known_article_fk` / `DERIVED_CASCADE_TABLES` (the FK guard) to where it stays live |
| Non-news cleanup (`non_news_cleanup.py`, script) | finished (plan 2026-10-10) | no code doc; delete together with legacy cleanup or keep as tools |
| Article evidence cache | live (daily enrichment) | covered by the future `core/daily/enrichment.md` |

## Weekly v2 (deferred, list only)

`core/weekly/*.py`, `storage/weekly.py`, `storage/repos.py` (`WeeklyAnalyticsRepo`),
`scripts/weekly_frozen_report.py`, `scripts/run_weekly_analytics_job.sh`.
`core/weekly/frozen.py` `code_hashes()` hashes its own file and `storage/reenrich_pilot_journal.py`;
any edit of either (including this PR's import re-pointing) makes existing frozen weekly runs
refuse to resume. Weekly is off in production, so this is accepted until weekly work starts.

## Other notes

- `core/daily/reenrich_pilot.py` still holds `ENDPOINTS` and the model names that
  `storage/daily_signals_ledger.py` and `core/daily/signals_extract.py` import; move them to
  `core/provider_costs.py` (or a `core/providers.py`) with the daily enrichment doc.
- `storage/weekly.py` has its own `encoded` / `fingerprint`; not merged with `journal_files.py`
  because weekly is deferred and its hashes are stored.
