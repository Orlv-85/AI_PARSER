# Feature Specification: Source Onboarding and Validation Workflow

**Feature Branch**: `003-source-onboarding-management`  
**Created**: 2026-02-28  
**Status**: Draft  
**Input**: User description: "хочу добавить фичу по добавлению новых сурсов: проверка на дубли, проверка работоспособности, хранение в БД, веб-интерфейс для bulk input текста с линками; начать со спеки/плана/tasks"

## Problem Context

Current source management is `sources.yaml`-centric. This does not scale for larger curated batches because:

- duplicate and near-duplicate sources are hard to detect before merge
- invalid candidate URLs (including search-wrapper URLs) can enter the pipeline
- HTML selectors cannot be validated before the source is manually committed
- onboarding a batch of sources is a manual, error-prone workflow
- there is no review state (`draft`, `validated`, `approved`, `rejected`)

The user provided a 50-source batch focused on AI-in-testing/QA. That batch already reveals the expected failure classes:

- some URLs are Google search wrappers instead of canonical source URLs
- some candidates are sections/tags rather than stable blog/feed roots
- some entries are likely duplicates or same-vendor overlaps (e.g. vendor blog + subtopic page on same domain)
- some sources are broad media portals that need classification and possible deprioritization

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bulk Intake of Raw Source Candidates (Priority: P1)

As an operator, I want to paste a raw block of URLs/text into the app and get normalized source candidates, so I can onboard large source batches quickly without manual YAML editing.

**Why this priority**: Without bulk intake, source growth remains manual and does not scale.

**Independent Test**: Submit a text block containing mixed plain URLs, markdown links, and prose; verify candidate URLs are extracted, normalized, deduplicated, and stored as drafts.

**Acceptance Scenarios**:

1. **Given** a text block containing 50 URLs and markdown links, **When** it is submitted to the onboarding form, **Then** the system extracts valid URLs and creates draft source candidates without requiring manual YAML edits.
2. **Given** repeated or syntactically different forms of the same URL, **When** intake runs, **Then** the system stores only one normalized draft candidate for that canonical URL.

---

### User Story 2 - Duplicate Detection and Source Family Grouping (Priority: P1)

As an operator, I want the system to detect exact duplicates and likely same-source overlaps, so I do not enable redundant sources that waste fetch time.

**Why this priority**: Duplicate source ingestion directly increases pipeline cost and content noise.

**Independent Test**: Feed a batch containing duplicate URLs, same-domain topic pages, and overlapping vendor pages; verify exact duplicates are blocked and likely overlaps are flagged for review.

**Acceptance Scenarios**:

1. **Given** two candidates with the same canonical URL, **When** they are imported, **Then** the second candidate is marked as duplicate and not stored as a separate active draft.
2. **Given** two candidates from the same vendor/domain that likely overlap (e.g. general blog plus narrow topic page), **When** analysis runs, **Then** the system flags them as a review group with a suggested preferred candidate.

---

### User Story 3 - Live Validation Before Approval (Priority: P1)

As an operator, I want to validate candidate sources before enabling them, so broken feeds, dead pages, and unusable HTML selectors are rejected early.

**Why this priority**: Validation is the only reliable way to stop bad sources from entering production fetch runs.

**Independent Test**: Run validation against a mixed set of RSS and HTML candidates; verify the system records fetch success/failure, classification, and extractor viability.

**Acceptance Scenarios**:

1. **Given** an RSS candidate with a reachable feed and entries, **When** validation runs, **Then** the candidate is marked valid with detected feed metadata.
2. **Given** an HTML candidate whose page loads but contains no usable article links, **When** validation runs, **Then** the candidate is marked failed or warning with a concrete reason.
3. **Given** a search-wrapper URL or unsupported non-canonical page, **When** validation runs, **Then** the candidate is marked invalid and not promoted.

---

### User Story 4 - Review and Promotion Workflow (Priority: P2)

As an operator, I want a review screen for draft candidates, so I can approve, reject, merge, or edit candidates before they become active fetch sources.

**Why this priority**: Draft-to-approved workflow is needed to keep source quality high as source volume grows.

**Independent Test**: Review a batch with mixed validation outcomes and duplicates; verify the operator can approve clean candidates and reject or merge noisy ones.

**Acceptance Scenarios**:

1. **Given** validated draft candidates, **When** the operator reviews them, **Then** approved candidates become active sources and rejected candidates remain excluded from fetch.
2. **Given** two duplicate/overlapping candidates, **When** the operator chooses merge or keep-preferred, **Then** the system preserves the canonical chosen source and records the relationship.

---

### User Story 5 - Controlled Interop with `sources.yaml` (Priority: P2)

As a developer/operator, I want `sources.yaml` to remain a controlled seed/export artifact rather than the primary editing surface, so source management can move to DB without losing bootstrap and backup capability.

**Why this priority**: Existing workflows depend on `sources.yaml`, but it should stop being the operational source of truth.

**Independent Test**: Import from YAML into DB and export approved sources back to a deterministic YAML snapshot.

**Acceptance Scenarios**:

1. **Given** an existing `sources.yaml`, **When** bootstrap import runs, **Then** active sources are loaded into DB without duplicate rows.
2. **Given** approved DB-backed sources, **When** export runs, **Then** the generated YAML snapshot is deterministic and preserves required fields.

## Edge Cases

- Input contains markdown links, prose text, duplicate URLs, or malformed URLs.
- Candidate URL is a Google search-result wrapper rather than a direct canonical page.
- Candidate is a broad portal/tag page (`/tag/...`, `/category/...`) rather than a source root.
- Candidate is reachable but blocked by bot protection or returns anti-bot HTML.
- HTML page returns links, but most are navigation, tags, pagination, or off-topic pages.
- Same vendor appears as both general blog and a narrow topic subsection.
- Existing approved source already covers the candidate domain/feed.
- Bulk import is rerun with partially overlapping data.
- Validation succeeds initially but later becomes stale.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST store source records in the database as the primary operational source of truth for onboarding and approval state.
- **FR-002**: System MUST support draft source candidates separate from active approved sources.
- **FR-003**: System MUST provide a bulk intake path that accepts raw text and extracts URLs from plain text and markdown links.
- **FR-004**: System MUST normalize candidate URLs before persistence (scheme, host casing, tracking cleanup where applicable, canonical wrapper rejection).
- **FR-005**: System MUST reject exact duplicate candidates based on canonical URL.
- **FR-006**: System MUST detect and flag likely overlapping candidates (same-domain families or topic-path variants) for operator review.
- **FR-007**: System MUST classify candidates into at least `rss`, `html`, or `unknown` during validation.
- **FR-008**: System MUST validate candidate reachability and record validation result/status and reason.
- **FR-009**: System MUST, for RSS candidates, verify feed parsing and non-empty entry detection before approval.
- **FR-010**: System MUST, for HTML candidates, verify page retrieval and article-link extraction before approval.
- **FR-011**: System SHOULD attempt best-effort selector suggestion/probing for HTML candidates where possible.
- **FR-012**: System MUST provide a web UI to review draft candidates and see duplicate/validation state.
- **FR-013**: System MUST allow operator actions: approve, reject, disable, merge/mark duplicate, and edit core source fields before approval.
- **FR-014**: System MUST keep approved sources available to the fetch pipeline without requiring manual edits to `sources.yaml`.
- **FR-015**: System MUST support one-way bootstrap import from `sources.yaml` into DB.
- **FR-016**: System SHOULD support deterministic export of approved sources back to YAML snapshot format.
- **FR-017**: System MUST record validation timestamps and allow stale validation status to be surfaced in UI.
- **FR-018**: System MUST expose batch onboarding and validation through deterministic code paths (CLI/API), not rely on ad hoc AI/manual editing.

### Key Entities *(include if feature involves data)*

- **SourceCandidate**: Draft source proposed from bulk intake, carrying raw input, normalized URL, inferred type, validation status, and review metadata.
- **ManagedSource**: Approved operational source stored in DB and consumed by fetch/update flows.
- **SourceValidationRun**: Validation result for a source candidate or managed source, including status, timestamps, detected type, errors, and probe metrics.
- **SourceDuplicateGroup**: Relationship grouping exact duplicates or likely overlaps, with a preferred canonical candidate/source.
- **SourceImportBatch**: Metadata about a pasted/uploaded batch, including original raw text, parsed candidate count, accepted count, rejected count.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A raw batch of 50 candidate links can be ingested into draft records in one action, with at least **95%** of syntactically valid URLs extracted correctly.
- **SC-002**: Exact duplicate candidate URLs are blocked with **100%** precision for normalized canonical duplicates in test fixtures.
- **SC-003**: Live validation provides a deterministic `valid/warning/failed` result for at least **90%** of test candidates without manual intervention.
- **SC-004**: Operators can review and approve/reject an onboarding batch from the web UI without editing `sources.yaml` directly.
- **SC-005**: Approved sources become available to fetch logic from DB without introducing duplicate active sources.
- **SC-006**: Existing `sources.yaml` can be imported into DB and re-exported deterministically for backup/bootstrap.
