# Non-news ingestion filter and proposed cleanup

Production was read using SSH and a PostgreSQL `REPEATABLE READ / READ ONLY`
transaction on 2026-10-10 at 16:30:02 UTC. No collector, model, weekly worker,
historical run, migration, publication, deletion or deployment was invoked.
The observed production weekly v2 flag was **false**. Repository variables and
cron settings were not changed.

## Cause and fix

DB-managed HTML sources are converted to `SourceConfig` with empty HTML options.
Unlike YAML sources, these sources have no stored CSS selectors. The default
parser scans every anchor in the document, including menus, product links,
footer links, directories and the source page itself. Both the two-stage and
legacy HTML paths accept their extracted text as articles. Missing publication
dates then receive `datetime.now(UTC)` at persistence, creating an apparent
publication burst during recovery. The burst is not itself evidence of garbage.

The new filter drops navigation/footer anchors and exact corporate, directory,
taxonomy and verified product paths before downloading article pages. After
download, page schema and body commerce cues identify further non-articles
before text extraction. Positive article schema/metadata and editorial paths
protect articles, research and product releases. Dates never determine page
eligibility. RSS entries, optional linked RSS text extraction, and both pipeline
persistence paths use the same guards before relevance model calls and input
observations. Canonical deduplication remains unchanged.

Audited managed list URLs for Kobiton, Qualitest, Autify and Codium/Qodo now get
specific article-link selectors. These records are in the DB, not in
`sources.yaml`; therefore no YAML entry or source was removed or rewritten.
Live page probes retained 11 Kobiton, 12 Qualitest, 6 Autify and 55 Qodo links.
Qualitest currently uses `/insights/blogs/` in article links; the selector also
supports its earlier `/insights/blog/` layout. Autify Genesis is an audited exact
landing path (including its `/products/autify-genesis` successor), not a ban on
the word "genesis". See the [Autify product page](https://autify.com/genesis).

The legacy date fallback remains unchanged for compatibility. Legitimate
undated news is retained; its stored timestamp must not be interpreted as
verified publication evidence. Ambiguous pages are retained by default.

## Concrete dry-run set

The complete candidate list (ID, URL, title, source, reason), uncertain list,
dependency IDs and proposed deletion IDs are in
[non-news-cleanup-2026-10-10.json](non-news-cleanup-2026-10-10.json).
No production rows have been deleted.

| Result | Count |
|---|---:|
| Articles scanned | 8,336 |
| Confident proposed article deletions | 313 |
| Uncertain records, excluded from deletion set | 185 |
| Corporate pages | 41 |
| Directory pages | 94 |
| Site home pages | 67 |
| Taxonomy/pagination pages | 109 |
| Verified Autify Genesis landing pages | 2 |

The uncertain set contains 144 commercial-section pages requiring review and
41 pages with commerce text cues. Extracted text alone cannot prove that they
lack independent editorial material, so they are not proposed for deletion.

The proposed-set SHA-256 is
`ccf6c5d891e3f295864c55a6ddd77aaaac14a2727881cf76a8cdc3a0b82b4e68`.
It freezes IDs, URLs, titles, sources, reasons and stored timestamps; future
approval must refer to this artifact, not to a freshly computed larger set.

| Original window | All articles | Confident | Uncertain |
|---|---:|---:|---:|
| September 28 through October 4 UTC | 1,021 | 174 | 123 |
| October 4, 19:00 through 19:59 UTC | 728 | 172 | 123 |

756 records in the week are dated October 4. Of the recovery-hour records,
433 are in neither candidate group. These groups do not establish that the
remaining records are accurately dated news.

| Known example | ID | Reason |
|---|---:|---|
| kobiton.com/about-kobiton | 94020 | corporate_page |
| qualitestgroup.com/about-us | 94098 | corporate_page |
| qualitestgroup.com/about-us/leadership-team | 94099 | corporate_page |
| qualitestgroup.com/about-us/board-of-directors | 94100 | corporate_page |
| autify.com/about | 94201 | corporate_page |
| autify.com/genesis | 94197 | verified_product_landing |
| qodo.ai/about | 94231 | corporate_page |

## Dependencies and consequences

The schema has one article foreign-key dependent table: `article_aliases`.
The snapshot contains zero aliases, so zero alias deletions are proposed.
The export includes all articles and sources and the related tables below.
The dry-run resolves exact/canonical URLs, article IDs and canonical hashes
inside frozen JSON, and follows parent report and publication relationships.

| Affected saved records | Count |
|---|---:|
| Digest items | 104 |
| Digest groups / reports | 13 / 6 |
| Legacy weekly items / reports | 3 / 2 |
| Weekly jobs | 1 |
| Weekly snapshots / publication pointers | 1 / 1 |
| Weekly observations / decisions | 0 / 0 |

The affected snapshot is
`816986e907ebf2ec3288b4b4c0d747a1dc5dfebdd5fe73235222b2c7ecbbff7a`.

Deleting the proposed articles would remove them from live article queries.
Digest/legacy weekly items store copied URLs, not article foreign keys; deleting
articles will leave those historical outputs unchanged. Frozen jobs and
snapshots also remain unchanged and can still contain these pages and their
counts. This proposal does not delete or regenerate reports, summaries,
observations, decisions, snapshots or publication pointers. Embedded narrative
text may mention a page without an explicit reference; the reported dependency
counts cover structured references, not inferred narrative mentions.

## Reproduce and restore

From the repository root, using an existing consistent export:

```sh
./venv1/bin/python scripts/non_news_cleanup.py \
  --export /path/to/non-news-production-export.json \
  --output /path/to/new-cleanup-directory
```

For a fresh read-only DB export, set `AINEWS_DATABASE_URL` through the usual
environment mechanism and omit `--export`. The command has no deletion option.
It creates `dry-run.json`, `backup.json` and `restore.sql` with mode 0600;
an existing output directory is refused rather than overwritten.

`backup.json` contains the complete exported ingestion/report tables, including
the proposed article rows and their texts. `restore.sql` restores only the
proposed article/alias rows with their original IDs, hashes and timestamps,
articles first, within one transaction. It requires the original sources to
remain present. On a disposable DB, delete only the proposed IDs and execute
the restore SQL with `psql --set ON_ERROR_STOP=on --file restore.sql`; duplicate
IDs cause failure rather than overwriting unrelated records. Do not execute it
against an unchanged production DB. A local SQLite delete/restore roundtrip
test verifies row counts, aliases, quoting and preservation of IDs.

Before any separately approved production removal, retain these backups outside
ephemeral storage, take a fresh full PostgreSQL backup, verify the approved rows
still match the frozen set, and check for new aliases/dependencies under a
consistent transaction. New records must not silently join the approved set.

## Validation

Regression tests cover all supplied garbage URLs, both HTML parsers, navigation
exclusion, undated news, product releases/research, RSS linked-page rejection,
legacy HTML fetch, both pipeline item paths, batch/per-row persistence and
deduplication, dependency reporting and backup restoration.

Final gates passed: `make lint PYTHON=./venv1/bin/python` (Ruff, mypy,
pylint 10.00/10) and `./venv1/bin/pytest` (677 passed, 2 skipped).
The two PostgreSQL integration tests were skipped because
`AINEWS_TEST_POSTGRES_URL` was not set. Restore SQL was roundtrip-tested against
SQLite; a separate PostgreSQL restore rehearsal was not performed. Production
foreign keys were independently checked read-only and confirm that only
`article_aliases.article_id` references `articles.id`.
