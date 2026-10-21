# Legacy article cleanup with JEV

> Archived 2026-10-21: the cleanup ran on 2026-10-11 and its code (`scripts/legacy_articles_cleanup.py`,
> `storage/legacy_cleanup.py`, `storage/cleanup_journal.py`, their tests) was removed in PR
> "chore: remove the finished one-off cleanup tools". The reject verdict lives on in
> `core/ingestion/reject_policy.py`, the snapshot helpers in `storage/article_snapshot.py`.
> To restore the tool: `git checkout 5323c5a -- scripts/legacy_articles_cleanup.py
> src/app/storage/legacy_cleanup.py src/app/storage/cleanup_journal.py src/app/storage/non_news_cleanup.py
> src/app/core/ingestion/legacy_cleanup.py tests/unit/test_legacy_cleanup.py`
> (the restored files import each other by their old names).

`scripts/legacy_articles_cleanup.py` evaluates a frozen, consistent database
snapshot. It sends only saved title (1,024 characters), summary (4,000), and
content (16,000) to the ordinary `JevRelevanceScorer`, including its unchanged
semantic admission question. It does not crawl, invoke DeepSeek, generate
weekly analytics, or change retention.

## Destructive decision policy

An existing valid accept with the current canonical URL/evidence/model/policy/
prompt cache key is kept without another request. AI editorial news, research,
reviews, tutorials and evergreen guides are accepted under the ordinary policy.
Dates, rank, category and old keyword scores do not decide deletion.

Cleanup policy `legacy-cleanup-1` requires an explicit semantic reject and
admission confidence >= 0.95. A non-AI reject additionally requires JEV relevance
<= 0.05 and at least 160 characters of saved body/summary. A non-editorial reject
additionally requires the existing deterministic URL/text filter to corroborate
the result. For example, About + confident non-editorial is a deletion candidate;
an AI release marked accepted is kept even with commerce cues. A non-AI verdict
with only a short snippet, contradictory relevance, or lower/missing confidence
is unresolved and kept. Invalid responses and provider failures stop screening.

These thresholds deliberately favor false negatives over destructive false
positives. They are operational guardrails, not a validated probability of
correctness. The two model outputs are correlated, not independent assessments.
The manifest records the actual probabilities, deterministic filter and basis;
JEV does not generate a textual rationale.

## Artifacts and spend limits

Prepare a private run directory from a read-only repeatable-read export including
all `EXPORT_TABLES`, plus `screening.model`, `screening.policy_version` and
`screening.prompt_version`. Dates are normalized before fingerprinting.

```sh
rtk proxy ./venv1/bin/python scripts/legacy_articles_cleanup.py prepare \
  --snapshot /private/path/export.json --run-dir /private/path/run
rtk proxy ./venv1/bin/python scripts/legacy_articles_cleanup.py screen \
  --run-dir /private/path/run --budget-usd 2 --max-requests 8287 --concurrency 8
rtk proxy ./venv1/bin/python scripts/legacy_articles_cleanup.py status \
  --run-dir /private/path/run
```

`screen` requires a JEV key in the usual environment. Limits are cumulative over
the journal, including restarts and failed/unknown attempts. Each request first
reserves 64,000 input tokens at the configured $0.042/M input rate. Reservations
are reduced only with valid returned usage. Output is free. Provider response
usage/cost fields are preserved privately; `usage_priced_usd` is computed from
usage, not claimed to be a provider invoice. Unknown usage retains the maximum
reservation. No automatic retry runs. A lost request with unknown outcome stops
resume for operator review; a received response is durably stored before parsing
so a crash cannot cause that successful evaluation to be paid again.

At most eight requests can be in flight. On failure/limit no new requests start;
already dispatched requests finish and are journaled. The same run directory
cannot be opened twice concurrently. Model/policy/prompt/evidence changes cannot
silently reuse a different run. Confirm current provider pricing before starting:
[official JEV models/pricing](https://docs.typesafe.ai/models).

The private files include snapshot, manifest, SQLite response/usage journal,
usage report, restore verification, rehearsal backup and apply backup/result.
Snapshots contain article text and are operational backups, not public assets.

For a later policy review, run the offline `review --run-dir /private/path/run`
command. `review-unresolved.json` lists every preserved ambiguous article with
ID, URL, original assessment, confidence, bounded evidence hash, dependencies,
text excerpt and specific failed guardrails. The complete text remains in the
snapshot and the actual responses in the journal. New deterministic thresholds
can be evaluated against these saved assessments without paid model calls.
Changes to the JEV question/model require a new version and paid evaluation of
the explicitly selected review set, under a new budget. Any new deletion set
must get its own manifest, current-row checks, backup and PostgreSQL rehearsal.

## PostgreSQL rehearsal and apply

Create an empty, isolated **local** PostgreSQL database called
`legacy_cleanup_test` or `legacy_cleanup_rehearsal`. Set
`AINEWS_CLEANUP_TEST_DATABASE_URL` using the normal
private environment mechanism, pointing to localhost. `rehearse` loads the
snapshot into that database, deletes precisely the proposed rows, inserts a
post-snapshot probe, restores deleted rows and previous cache decisions, and
checks all exported tables and preservation of the probe. It refuses a nonempty
database, SQLite, a remote host, or another database name.

```sh
rtk proxy ./venv1/bin/python scripts/legacy_articles_cleanup.py rehearse \
  --run-dir /private/path/run
```

Before production apply, retain a private full PostgreSQL backup, coordinate the
collector and any cron-triggered collection, confirm ordinary admission stays
enabled and weekly flag/cron stay off. Copy the verified code and private run
artifacts to the production operational directory. Use the existing runtime
environment for `AINEWS_DATABASE_URL` and screening settings. Then:

```sh
rtk proxy python scripts/legacy_articles_cleanup.py apply \
  --run-dir /private/path/run --collector-coordinated
```

Apply requires a restore receipt matching both snapshot and manifest hashes.
Within one transaction it locks the exported dependency tables, verifies actual
article foreign keys, compares entire article/evidence/dependency fingerprints,
and skips changed rows. Only aliases and exact confirmed article IDs are deleted.
Admission rejects are committed in the same transaction under the ordinary cache
key; older pending entries for those canonical hashes are settled without
assigning a rejection to their unevaluated text. A complete targeted backup is
fsynced before mutation. Repeat apply recognizes already committed IDs and
refuses conflicting/incomplete backup state. Errors roll back aliases, articles
and cache together.

Digest groups/items/reports, legacy weekly items/reports, observations, decisions,
jobs, snapshots and publications are inventoried and retained. Copied URL/text
references remain in those outputs; unlinked prose mentions cannot be inferred
completely. No narrative, metric, frozen snapshot or full report is regenerated.

`restore_cleanup(engine, backup)` is the targeted rollback API. It restores
articles before aliases and restores only affected admission keys, refusing ID,
canonical URL and cache conflicts. It does not truncate tables, reset production
sequences or overwrite post-snapshot data. Inspect the apply backup and result
before invoking rollback; retain the private backup outside ephemeral storage.

Run scoped cleanup tests with `AINEWS_TEST_POSTGRES_URL` pointing to an isolated
database. Before commit/push run `make lint PYTHON=./venv1/bin/python` and the
complete test suite. Never use production as a test database.
