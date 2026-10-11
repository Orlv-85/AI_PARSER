# Article re-enrichment and publication dates

This change separates source publication, modification and discovery dates and
provides tools for a frozen, resumable review of existing articles. The applied
production operation is recorded in
[the outcome report](reenrich-production-results-2026-10-11.md).

## Application behavior

`published_at` is nullable. Missing source dates no longer become the time of
collection, and RSS `updated` no longer substitutes for `published`.
`modified_at` stores a separate source modification timestamp. The original
`discovered_at` is preserved.

`publication_day` stores a known calendar date when the source does not provide
an unambiguous timestamp with a timezone. It participates in day filtering and
daily publication counts without inventing a time. `publication_status` records
`confirmed`, `unknown`, `conflict` or `legacy_unverified`;
`publication_precision` and `date_provenance` describe the evidence.

HTML ingestion reads Article JSON-LD, publication/modification meta tags and
microdata before scripts are removed. Conflicting candidates are retained as
conflicts. Visible time labels are retained for later review rather than guessed.
RSS preserves the original publication and modification literals and avoids
feedparser's published/updated field aliases.

CLI, MCP and web API responses support unknown timestamps. Web news, export,
article detail and link-feed responses expose publication evidence and optional
enrichment metadata. Existing API fields remain; `published_at` can now be null.
The news UI shows calendar dates without a fabricated time and labels unknown
publication dates. Queries and pruning account for known calendar dates;
records with neither a timestamp nor a calendar date are not age-pruned.
Timestamp sorting puts null values last.

## Topic and enrichment metadata

The ten reviewed re-enrichment topics are readable and filterable alongside
legacy categories. `material_type` separates format, including `Comparison`,
from topic. `compared_products` stores supported product names as JSON.
`enrichment_provenance` records the saved assessment and grounded summary
provenance; source pages, responses and supporting quotes remain in private
operational artifacts.

The ordinary JEV category/admission rubric remains pinned to its previous
criteria. `JevRelevanceScorer.questions()` exposes that rubric for criteria-aware
pilot requests. This release does not automatically schedule re-enrichment,
replace the ordinary category rubric with all ten reviewed topics, or connect
the new summary journal to daily digest publication. Those integration changes
are a separate task. Existing daily digest scheduling and fallback behavior
are unchanged.

## Modules and tools

| File | Responsibility |
| --- | --- |
| `src/app/ingest/date_evidence.py` | Literal date parsing, precision, timezone and conflict resolution |
| `src/app/storage/article_evidence_cache.py` | Private page cache, redirect/robots checks, per-host pacing and extraction quality |
| `scripts/reenrich_articles.py` | Freeze URLs, download/resume, verify artifacts and audit saved date proof |
| `src/app/core/reenrich_pilot.py` | Versioned JEV questions, conservative decisions and quote-grounded summary parsing |
| `src/app/storage/reenrich_pilot_journal.py` | Durable provider responses, spend reservations, usage and controlled recovery |
| `scripts/reenrich_pilot.py` | Frozen mixed pilot, response reuse and aggregate reporting |
| `src/app/storage/reenrich_apply.py` | Manifest verification, transactional updates/deletions and targeted restore |

Download and pilot commands are documented in
[the source-cache guide](article-source-cache.md) and
[pilot preparation](reenrich-pilot-preparation-2026-10-11.md).
The validated candidate rubric is saved in
[the clarification artifact](reenrich-jev-rubric-clarification-2026-10-11.json).
The one-time mass orchestration scripts and full-data rehearsal receipts are
private under `tmp/reenrich-2026-10-11/`; they are not scheduled application jobs
or included in the repository.

Fetching/extracting pages uses ordinary code. JEV assesses bounded source text;
DeepSeek generates English summaries of accepted articles. Model responses and
payments are journaled before reuse. Exact source quote checks are safeguards,
not a guarantee of semantic correctness. Invalid responses and unknown billing
stop processing for review. Source errors, poor extraction and ambiguous model
decisions do not authorize deletion.

## Schema, apply and rollback

Migration `a42b750d0c44`, after `f31a640c9b33`, adds the evidence/enrichment fields
and makes `published_at` nullable. Ordinary Alembic upgrade is required before
running this application version. Existing rows start as `legacy_unverified`.
Downgrade refuses existing null publication timestamps instead of fabricating
dates to satisfy the previous non-null constraint.

`apply_reenrichment(engine, manifest, backup_path)` verifies manifest hashes,
article identities and conservative deletion evidence. It locks dependency
tables, compares live row/dependency fingerprints, skips concurrent drift and
saves a private targeted backup before mutation. Updates, exact-ID deletions,
alias removal and assessment ledger inserts share a transaction. A matching
backup supports idempotent apply; conflicting state is refused.

`restore_reenrichment(engine, backup)` restores only affected rows and assessment
keys. It refuses conflicting current rows/ledger records, restores articles
before aliases and leaves unrelated post-snapshot rows intact. Keep the full
database backup as well as targeted receipts. Rehearse apply and restore on an
isolated PostgreSQL database before changing production data.

Copied digest/weekly URLs, text and frozen snapshots are not rewritten by article
cleanup. Retention remains 800 days, with the existing 5 GiB size threshold and
4 GiB target. Corrected dates can make additional rows eligible for the next
ordinary prune; the outcome report records that impact.

## Validation

Relevant tests cover date evidence and unknown dates, RSS aliases, page-cache
resume/privacy, source quality, provider journals/budgets, grounded summaries,
manifest safety, day filtering/statistics and null-safe API responses.
Run `make lint PYTHON=./venv1/bin/python` and the full pytest suite before
commit/push. Use a separate file-backed SQLite database and explicit test auth
settings locally. Optional PostgreSQL tests require `AINEWS_TEST_POSTGRES_URL`;
the production operation also has separate PostgreSQL 14/18 full-data receipts.
