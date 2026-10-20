# Implementation Plan: Source Onboarding and Validation Workflow

**Branch**: `003-source-onboarding-management` | **Date**: 2026-02-28 | **Spec**: `specs/003-source-onboarding-management/spec.md`  
**Input**: Feature specification from `specs/003-source-onboarding-management/spec.md`

## Summary

Move source onboarding from manual YAML editing to a controlled DB-backed workflow:

1. Introduce DB-backed draft and approved source models.
2. Add bulk intake that parses raw text into candidate URLs.
3. Add static dedup/overlap analysis before validation.
4. Add live validation for RSS/HTML candidates.
5. Add a web review UI to approve/reject/merge candidates.
6. Keep `sources.yaml` as bootstrap/import and optional export, not the primary editing path.

This sequence solves immediate scaling pain while preserving backward compatibility with current source bootstrapping.

## Technical Context

**Language/Version**: Python 3.14.x  
**Primary Dependencies**: FastAPI, Typer, SQLAlchemy, httpx, feedparser, lxml, existing source onboarding helper utilities  
**Storage**: PostgreSQL (primary operational storage), SQLAlchemy ORM  
**Testing**: pytest, pytest-cov, mypy, ruff, pylint  
**Target Platform**: Linux VPS (Docker Compose, Caddy reverse proxy)  
**Project Type**: Single Python app (CLI + Web API/UI)

**Constraints**:
- Preserve current fetch behavior while source management migrates to DB
- Avoid breaking existing `sources.yaml` bootstrap workflows
- Keep source quality gates deterministic and code-driven
- Prevent duplicate active sources from entering production fetch runs
- Keep onboarding UI simple enough for bulk ops, not a full CMS

## Constitution Check

### Pre-Implementation Gate (Pass)

- Spec exists and defines measurable onboarding outcomes: PASS
- Explicit approval is required before implementation: PASS
- No production code changes before approved spec/plan/tasks: PASS
- The workflow can be delivered incrementally: PASS

## Current-State Assessment

### What exists already

- `sources.yaml` holds source configuration and acts as the current source registry.
- `scripts/sources_onboarding_helper.py` provides partial lint/probe support for YAML-based onboarding.
- The fetch pipeline already persists `Source` rows for runtime fetch metadata.

### What is missing

- No DB-backed draft lifecycle for candidate sources
- No bulk raw-text onboarding endpoint/UI
- No canonical duplicate management for onboarding
- No review queue/status model
- No stable live validation state for candidates
- No first-class operator workflow for source approval

## Domain Findings from the Provided 50-Source Batch

The provided QA/AI-testing batch confirms the need for this feature:

1. **Search-wrapper URLs must be rejected**
- Some provided links point to Google search URLs rather than the real source page.
- These must fail canonical validation immediately.

2. **Vendor overlap must be modeled**
- Some candidates are likely same-vendor overlaps (general blog vs narrow AI/testing subpage).
- Exact duplicates are not enough; we need review grouping.

3. **Broad media/tag pages need classification**
- Portals like topic/tag sections may be valid but lower quality as "source roots".
- The system should classify them and surface warnings rather than silently approving.

4. **RSS should be preferred where discoverable**
- For blog roots, validation should detect or prefer feed endpoints when available.

## Target Architecture

### A. DB-backed Source Registry

Add explicit source management entities:

- `SourceCandidate` (draft intake/review lifecycle)
- `ManagedSource` (approved operational source; may extend or evolve current `Source` semantics)
- `SourceValidationRun`
- `SourceDuplicateGroup` / duplicate links to preferred source
- `SourceImportBatch`

Design choice:
- Keep fetch pipeline reading approved sources only.
- Draft candidates stay isolated until operator approval.

### B. Intake Pipeline

1. Raw text submission (web + CLI/API)
2. URL extraction
3. URL normalization/canonicalization
4. Exact dedup
5. Overlap heuristics (same host, path-family, known source family)
6. Draft persistence

### C. Validation Pipeline

Validation should be deterministic and idempotent:

- `rss` path:
  - fetch URL (or discovered feed)
  - parse feed
  - confirm entries exist
- `html` path:
  - fetch page
  - extract candidate article links
  - score link quality / warn on broad selectors
- `unknown` path:
  - classify as failed or warning for manual review

Validation output is stored and displayed, not just logged.

### D. Review Surface

A dedicated web page should support:

- viewing import batch summary
- filtering drafts by status (`new`, `duplicate`, `validated`, `failed`, `approved`, `rejected`)
- reviewing duplicate groups
- reviewing validation errors/warnings
- editing core fields before approval
- approval/rejection actions

### E. YAML Interop

Short-term compatibility:

- bootstrap import current `sources.yaml` into DB
- optionally export approved sources back to YAML snapshot

Long-term intent:
- DB is primary operational truth
- YAML is seed/backup, not the main editor

## Phased Delivery Strategy

### Phase 1 (P1, MVP foundation)

- DB schema for source candidates, import batch, validation result metadata
- URL extraction + normalization + exact dedup
- CLI/API bulk intake endpoint
- Basic draft persistence

### Phase 2 (P1)

- Live validation engine for RSS/HTML candidates
- Duplicate-family heuristics
- Validation status persistence and surfacing

### Phase 3 (P1/P2)

- Web review UI for drafts and duplicate groups
- Approve/reject/edit actions
- Approved-source handoff to fetch pipeline

### Phase 4 (P2)

- `sources.yaml` bootstrap import and deterministic export
- Tighten helper tooling (`scripts/sources_onboarding_helper.py`) to work with DB-backed registry too

## Heuristic Rules (MVP)

### Exact duplicate rules

- Same normalized canonical URL => exact duplicate
- Same URL after stripping query tracking params => exact duplicate
- Search-engine wrapper URLs => invalid, never a candidate source

### Likely overlap rules

- Same host + one path is strict prefix of another (`/blog` vs `/blog/ai-test-automation`)
- Same host + topic/category/tag page variant
- Same vendor root with one feed and one HTML page pointing to same content family

### Validation statuses

- `pending`
- `validated`
- `warning`
- `failed`
- `approved`
- `rejected`
- `disabled`

## Risks and Mitigations

### Risk 1: Schema overlap with existing `Source` table
- Mitigation: Introduce new onboarding entities first; avoid overloading runtime `Source` until approval workflow is stable.

### Risk 2: False positives in overlap heuristics
- Mitigation: Treat likely overlaps as review warnings, not auto-rejections.

### Risk 3: Validation noise from bot protection or unstable sites
- Mitigation: Distinguish `warning` from hard `failed`; retain manual override.

### Risk 4: Source-of-truth migration confusion
- Mitigation: Explicitly document DB-primary / YAML-secondary model and keep deterministic import/export.

## Project Structure

### Documentation (this feature)

```text
specs/003-source-onboarding-management/
├── spec.md
├── plan.md
└── tasks.md
```

### Expected Code Areas

```text
src/app/
├── cli/main.py
├── config/sources.py
├── core/
│   ├── canonicalize.py
│   └── source_onboarding.py         # new helper/service module (likely)
├── ingest/
│   ├── fetcher.py
│   ├── rss.py
│   └── html.py
├── storage/
│   ├── models_sql.py
│   ├── repos.py
│   └── db.py
├── web/
│   ├── app.py
│   ├── models.py
│   ├── service.py
│   └── templates/index.html or new onboarding template
scripts/
└── sources_onboarding_helper.py
```

## Approval Gate

Per `spec-first-multi-agent`, implementation should not begin until the user approves this spec and plan.
