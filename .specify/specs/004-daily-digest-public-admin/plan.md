# Implementation Plan: Public Daily Digest and Admin Separation

**Branch**: `004-daily-digest-public-admin` | **Date**: 2026-03-01 | **Spec**: `.specify/specs/004-daily-digest-public-admin/spec.md`  
**Input**: Feature specification from `.specify/specs/004-daily-digest-public-admin/spec.md`

## Summary

Split the current web app into two distinct surfaces:

1. A **public daily digest** at `/`, readable without auth and optimized for consumption.
2. A **private admin console** at `/admin`, protected by the existing password gate and containing the operational UI.
3. A stable app-side **digest API contract** that lets an external client fetch article links for a day, generate grouped summaries externally, and post the final digest back for public rendering.

This keeps the AI summarization worker outside the app process while making the app the durable source of truth and public presentation layer.

## Technical Context

**Language/Version**: Python 3.14.x  
**Primary Dependencies**: FastAPI, SQLAlchemy, existing web auth/session code, existing web shell and article storage  
**Storage**: PostgreSQL (primary), SQLAlchemy ORM  
**Testing**: pytest, pytest-cov, mypy, ruff, pylint  
**Target Platform**: Linux VPS (Docker Compose, Caddy reverse proxy)  
**Project Type**: Single Python app (Web + CLI + background fetch)

**Constraints**:

- Keep auth logic simple: reuse existing admin login/session model
- Public digest routes must be explicitly whitelisted from auth middleware
- Admin APIs must remain protected after route reorganization
- Do not couple server runtime to desktop-only tools like Tauri apps
- Public UI should be simple, readable, and mobile-safe
- Existing update/onboarding behavior should remain logically unchanged

## Constitution Check

### Pre-Implementation Gate (Pass)

- Spec exists and defines measurable routing/API/UI outcomes: PASS
- Explicit approval is required before implementation: PASS
- No production code changes before approved spec/plan/tasks: PASS
- The feature can be delivered in small slices with clear review gates: PASS

## Current-State Assessment

### What exists already

- FastAPI app with existing auth middleware and login flow
- A single web shell (`src/app/web/index.html`) mixing update, parsed news view, and onboarding tools
- Public-ish `/api/news` and `/api/news/{article_id}` data endpoints
- Existing article persistence and date filtering in `ArticleRepo`
- Existing admin update/onboarding operational flows

### What is missing

- A dedicated public digest entity in storage
- A public digest page distinct from the admin shell
- Route-level separation between public and admin web surfaces
- A date-scoped link feed endpoint specifically intended for external summarization clients
- A digest submission endpoint that persists grouped reports for public rendering

## Target Architecture

### A. Route Split

Separate the app into two web entrypoints:

- `/` -> public digest page (no auth)
- `/admin` -> authenticated admin shell

Supporting routes:

- public digest JSON APIs remain unauthenticated
- operational `/api/update/*`, `/api/source-onboarding/*`, and admin shell stay behind auth

This likely requires tightening the auth middleware from a broad "all `/api`" rule to an allowlist/denylist model.

### B. Digest Storage Model

Add three DB-backed entities:

- `NewsDigestReport` keyed by `report_date`
- `NewsDigestGroup` linked to a report
- `NewsDigestItem` linked to a group, optionally referencing an existing article/source

Design choice:

- The digest is stored as an application-owned publication artifact.
- The external agent can regenerate a day and replace the stored report deterministically.

### C. External Agent Contract

The app should define a stable API contract for external tooling:

1. **Fetch link feed**
- Input: date, limit, optional relevance threshold
- Output: canonical article links and metadata for that date

2. **Submit digest**
- Input: date + grouped digest payload
- Output: stored digest representation

3. **Read digest**
- Input: date
- Output: grouped digest representation for page/API rendering

This keeps OpenClaw/PocketPaw/Antigravity orchestration outside the server and avoids shipping GUI runtimes into production containers.

### D. Public UI

The public digest page should:

- default to today's UTC date
- allow another date to be selected
- show a clear empty state if no digest exists
- render group sections with:
  - group title
  - entry title
  - short summary
  - outbound link

Visual direction:

- minimal, future-oriented, digest-first
- typography and spacing optimized for reading rather than operations

### E. Admin UI

The existing shell should be retained but moved under `/admin`:

- update run/status controls
- parsed news browsing/export helpers
- source onboarding import/review

Visual direction:

- still compact and utilitarian
- cleaner than the current raw shell
- visually distinct from the public digest

## Phased Delivery Strategy

### Phase 1 (P1, Data and Public Read Contract)

- Add digest storage models and repository methods
- Add public digest read API
- Add date-scoped link feed API

### Phase 2 (P1, Public Web Surface)

- Split root to public digest page
- Keep public routes unauthenticated
- Add digest page rendering and date picker UX

### Phase 3 (P1, Admin Relocation and Auth Hardening)

- Move existing operator shell to `/admin`
- Keep login flow and auth protection intact
- Ensure admin APIs remain private while digest APIs stay public

### Phase 4 (P1, External Digest Submission)

- Add digest submission API
- Support deterministic replace/update for same-date reports
- Add validation and error handling for malformed submissions

### Phase 5 (P2, Visual Refinement)

- Apply digest-first design polish to the public page
- Refresh admin shell styling while preserving functionality

## Risks and Mitigations

### Risk 1: Breaking auth boundaries during route split
- Mitigation: Add explicit tests for public routes vs protected admin routes before moving templates.

### Risk 2: Accidentally exposing admin APIs publicly
- Mitigation: Convert auth gating to explicit public-route allowlisting and test every relevant prefix.

### Risk 3: UI complexity from trying to keep both surfaces in one template
- Mitigation: Prefer separate templates or clearly separated render paths instead of overloading one page.

### Risk 4: Tight coupling to external agent tooling
- Mitigation: Keep the integration contract at the HTTP API boundary; do not make server startup depend on OpenClaw/PocketPaw or Antigravity binaries.

### Risk 5: Duplicate or inconsistent digest updates for the same date
- Mitigation: Enforce one canonical digest per date and replace child rows transactionally.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/004-daily-digest-public-admin/
├── spec.md
├── plan.md
└── tasks.md
```

### Expected Code Areas

```text
src/app/
├── storage/
│   ├── models_sql.py
│   ├── repos.py
│   └── migrations/
├── web/
│   ├── app.py
│   ├── auth.py
│   ├── models.py
│   ├── service.py
│   ├── index.html              # likely becomes admin shell
│   ├── digest.html             # likely new public template
│   └── login.html
tests/
├── unit/
│   ├── test_web_app.py
│   ├── test_web_digest_api.py
│   ├── test_auth_e2e.py
│   └── test_web_public_digest.py
└── e2e/
    └── test_api_e2e.py
```

## Implementation Notes

- Reuse `ArticleRepo.list_for_view()` date filtering semantics for the link feed to avoid a second definition of "which articles belong to a day".
- Prefer a dedicated digest template over conditional rendering inside the admin shell if template complexity grows.
- If admin/public route split causes auth middleware complexity, move to explicit route-prefix classification (`/`, `/digest`, public digest APIs) vs protected prefixes (`/admin`, admin APIs).
- The external client should own the Antigravity/OpenClaw/PocketPaw orchestration. The app should only expose the HTTP contract and persist/render results.

## Approval Gate

Per `spec-first-multi-agent`, implementation should not begin until the user approves this spec and plan.
