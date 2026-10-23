# Feature Specification: Full-text article archive (A1 storage, A3 daily capture)

**Feature Branch**: `016-article-archive`
**Created**: 2026-10-23
**Status**: Draft
**Input**: Backlog B3 (`docs/backlog/article-archive-todo.json`), tasks A1 and A3. Owner goal: keep the
full clean text of every collected AI article permanently, because source pages disappear; raw
material first, interpretation later. Owner decision 2026-10-23: start before weekly analytics.
A0 (off-site backups) is done.

Measured facts and the queries behind them: `records/report-plan-2026-10-23.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Collected text is never lost (Priority: P1)

As the owner, I want every stored article's metadata and source text copied into a private archive
that retention and cleanup never touch, so the corpus survives when `articles` rows are pruned and
when source pages disappear.

**Why this priority**: text is already being lost: every deploy runs `ai-news prune
--older-than-days 800`, and 79 stored articles (71 with full text) are older than that today.

**Independent Test**: insert articles, run the archive sync, run `prune`; the archive still holds
every document and text version.

**Acceptance Scenarios**:

1. **Given** an article with content of at least `ARCHIVE_MIN_TEXT_CHARS`, **When** the archive
   sync runs, **Then** one document and one text version (`origin = article_content`) exist.
2. **Given** an article older than the retention cutoff that is not archived yet, **When** `prune`
   runs, **Then** the article is archived first, in the same transaction, and then deleted.
3. **Given** an archived document, **When** the sync runs again with the same text, **Then** no new
   version is added; **When** the text differs, **Then** a new version is added and the old one stays.

### User Story 2 - Daily capture fills the gaps (Priority: P1)

As the owner, I want a nightly step that archives new articles and downloads the source page of
those stored without full text, politely and within a fixed budget, so coverage of new articles
reaches at least 90%.

**Why this priority**: since admission (2026-10-12) 92% of new articles already carry full text
from the fetch; the rest (openai.com 403, medium.com, Hugging Face items beyond the RSS full-text
cap) have title only, and their pages may disappear.

**Independent Test**: with a fake HTTP transport, run the capture over a window with one article
with content, one without content whose page extracts, one 404 and one 403; check states, versions,
attempts and the summary log.

**Acceptance Scenarios**:

1. **Given** an article without full text whose page was already downloaded and extracted by
   daily-publish, **When** the capture runs, **Then** that text is archived without a request.
2. **Given** an article without full text, **When** the capture downloads its page and extraction
   gives at least `ARCHIVE_MIN_TEXT_CHARS` with quality `extracted`, **Then** a version with
   `origin = source_page` is stored and the document is `archived`.
3. **Given** a 404, 410, robots disallow, non-HTML or redirect to a non-article, **Then** the
   document is `gave_up` at once; **Given** any other failure, **Then** it is retried after
   `ARCHIVE_RETRY_DELAYS` and is `gave_up` after the last delay.
4. **Given** the capture fails, times out or is skipped, **Then** fetch, digest, signals and their
   exit statuses are unchanged.

### User Story 3 - Operator purge (Priority: P2)

As the operator, I can remove archived documents for a URL, a source or a host on request (A7 opt
out), with a dry run by default.

**Independent Test**: `ai-news archive purge --host example.com` lists counts and deletes nothing;
with `--apply` it deletes those documents and their versions only.

### Edge Cases

- An article changes its stored content (re-enrichment never rewrites `content`, but a future path
  might): a new version, old version kept.
- Two URLs of one story: two documents (identity is the canonical URL hash, as in ingestion).
- The same canonical hash is pruned and later collected again: the existing document is reused,
  `article_id` points to the new row.
- A page grows, is paywalled or turns into a consent wall on retry: only `extracted` text of at
  least `ARCHIVE_MIN_TEXT_CHARS` becomes a version; issues are kept on the document.
- The capture is killed mid-run: every committed document stays; the next run continues (per-row
  commits, download cache is resumable).
- Archive size passes `ARCHIVE_SIZE_WARN_BYTES`: the summary log says so; nothing is deleted.
- Host lock is held by a long digest: the capture waits on the lock like the other jobs and gives
  up after the wait without an error exit.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The archive MUST live in two tables of the application database, `archive_documents`
  (one row per canonical URL hash) and `archive_texts` (text versions), with no foreign key to
  `articles` or `sources`.
- **FR-002**: A document MUST keep: canonical hash, URL, canonical URL, source key, host, title,
  publication date fields and status, the last known article id, first seen time, capture state,
  attempts, next attempt time and last issue.
- **FR-003**: A text version MUST keep: text, length, SHA-256 of the text, origin
  (`article_content` or `source_page`), extraction version, final URL, HTTP status (downloads),
  quality issues, capture time. A version is added only when its hash differs from every stored
  version of the document.
- **FR-004**: Raw HTML MUST NOT be stored in the database. Downloaded pages stay in the archive's
  file cache for at most `ARCHIVE_RAW_KEEP_DAYS`, then the capture deletes them.
- **FR-005**: `ai-news prune` MUST archive (metadata and content, no network) every article it is
  about to delete, in the same transaction, before the delete.
- **FR-006**: No retention, prune, cleanup or evidence purge path may delete archive rows. Only
  `ai-news archive purge ... --apply` deletes them.
- **FR-007**: No web page, API route or MCP tool may read the archive tables.
- **FR-008**: `ai-news archive capture` MUST (a) sync documents and `article_content` versions for
  articles first seen within `ARCHIVE_LOOKBACK_DAYS` (all articles with `--all`), without network;
  (b) for due documents of the window that still lack text, reuse an extracted page from the
  daily-publish source cache, else download through `SourcePageDownloader`; (c) stop dispatching
  downloads at `--max-seconds` and at the per-run caps; (d) never download with `--no-download`.
- **FR-009**: Downloads MUST respect robots.txt, per-host pacing and the crawl delay, the existing
  user agent, timeouts and body limit, the 429/503 host pause of `SourcePageDownloader`, plus a cap
  per run (`ARCHIVE_MAX_DOWNLOADS`) and per host (`ARCHIVE_MAX_PER_HOST`).
- **FR-010**: Permanent issues (`http_404`, `http_410`, `robots_disallowed_or_unavailable`,
  `non_html_response`, `redirect_to_non_article`) MUST set `gave_up` at once; other failures MUST
  set `next_attempt_at` from `ARCHIVE_RETRY_DELAYS` and `gave_up` after the last one.
- **FR-011**: The capture MUST end with one JSON log line `archive_capture_finished`: documents and
  archived documents of the window, coverage percent, new versions by origin, cache reuses,
  downloads, failures by issue, gave up, skipped by cap or time, archive size in bytes.
- **FR-012**: The capture MUST run as its own nightly systemd job under the shared host lock and its
  own time limit; its failure MUST NOT change any other job.
- **FR-013**: `ai-news archive purge` MUST select by `--url`, `--source` or `--host`, print counts,
  and delete only with `--apply`.
- **FR-014**: `ai-news archive status` MUST print counts by state, coverage of the last
  `ARCHIVE_LOOKBACK_DAYS`, top hosts without text, and table sizes (read-only).

### Key Entities

- **Archive document**: one collected URL identity (canonical URL hash) with metadata and capture
  state; outlives its `articles` row.
- **Archive text version**: one distinct clean text of a document with its provenance; append-only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the seed run, every stored article has a document; every article with content
  of at least `ARCHIVE_MIN_TEXT_CHARS` has a version (today 3030 of 7079).
- **SC-002**: For articles first seen in a 7-day window, at least 90% of documents have a text
  version of at least `ARCHIVE_MIN_TEXT_CHARS` once the window has passed (92% from fetch alone
  2026-10-12..23; target lifts gaps such as Hugging Face items beyond the RSS full-text cap).
- **SC-003**: Pruning or a deploy never reduces the number of archive documents or versions.
- **SC-004**: The nightly capture finishes within its limit (target under 15 minutes for a normal
  day of about 100 new articles) and has never changed the status of fetch, digest or signals.
- **SC-005**: Archive growth stays under 1 GB per year in the database (estimate 0.35 GB per year).

## Out of scope

- A2 backfill downloads of old articles (see `plan.md`, "Next spec: A2").
- A4 condensing, A5 extra fields (author, language, outbound links), A6 RAG, A7 legal review:
  the model leaves room (additive columns, derived tables keyed by text version id).
- Exposing archive text anywhere, including the admin pages (a count on the admin stats page is
  an optional last task).
