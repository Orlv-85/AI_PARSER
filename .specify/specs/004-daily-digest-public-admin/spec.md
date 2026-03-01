# Feature Specification: Public Daily Digest and Admin Separation

**Feature Branch**: `004-daily-digest-public-admin`  
**Created**: 2026-03-01  
**Status**: Draft  
**Input**: User description: "Daily Digest должен быть отдельной страницей в общем доступе; по умолчанию root ведет на digest; админка только через /admin по паролю; админка включает update/news/onboarding; нужен API для списка ссылок за день и приема сгруппированного digest-отчета от внешнего агента"

## Problem Context

Current web UX is operator-first:

- the main entrypoint is effectively an admin console
- the current UI mixes operational controls (update/onboarding) with end-user news viewing
- all useful news access is behind the same authenticated web shell
- there is no public-facing digest page with a stable daily permalink-like contract
- there is no dedicated app API contract for external agent tooling that fetches article links, generates grouped summaries, and posts the final digest back

The target product split is now different:

- **public users** should land on a clean, readable daily digest page
- **admins/operators** should use a separate password-protected `/admin` console
- **external automation clients** (OpenClaw/PocketPaw or similar) should call app APIs, not be embedded into the server UI

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Public Daily Digest as Default Entry (Priority: P1)

As a public visitor, I want the site root to open a readable daily digest page, so I can immediately see grouped AI news summaries without logging in.

**Why this priority**: This is the user-facing product surface and changes the app from an internal tool to a public news destination.

**Independent Test**: Open `/` while unauthenticated; verify the digest page loads, defaults to today's date, and renders grouped news if a digest exists.

**Acceptance Scenarios**:

1. **Given** an unauthenticated visitor, **When** they open `/`, **Then** they see the public digest page instead of the admin console.
2. **Given** a digest exists for today, **When** the page loads, **Then** the digest for today's date is shown by default.
3. **Given** a visitor chooses another date, **When** a digest exists for that date, **Then** the page reloads the selected day's grouped digest content.
4. **Given** no digest exists for the selected date, **When** the page loads, **Then** the page shows a clean empty state rather than a server error.

---

### User Story 2 - Protected Admin Console at `/admin` (Priority: P1)

As an operator, I want all update/onboarding/admin tools moved under `/admin` behind password auth, so operational controls stay private while the digest remains public.

**Why this priority**: Public content and operational tooling must be separated for security and clarity.

**Independent Test**: Open `/admin` without auth and verify a login challenge; authenticate and verify update/news/onboarding tools remain available there.

**Acceptance Scenarios**:

1. **Given** an unauthenticated request to `/admin`, **When** the route is opened, **Then** the user is redirected to login or shown the existing login gate.
2. **Given** an authenticated admin, **When** they open `/admin`, **Then** they see the existing operational console (update, parsed news tools, onboarding).
3. **Given** a public visitor on `/`, **When** they navigate the digest page, **Then** no admin controls or onboarding actions are exposed.

---

### User Story 3 - External Agent Link Feed and Digest Submission (Priority: P1)

As an external automation client, I want to fetch article links for a target date and submit a grouped digest report back to the app, so the app can act as the durable store and public renderer for AI-generated summaries.

**Why this priority**: Without a stable app-side API contract, the external summarization workflow is brittle and non-repeatable.

**Independent Test**: Fetch the link list for a given date, submit a grouped digest payload, then load the public digest page/API for that same date and verify the rendered content matches the submitted structure.

**Acceptance Scenarios**:

1. **Given** a target date, **When** the external client requests the link-feed endpoint, **Then** the app returns article links and metadata for that day only.
2. **Given** a grouped digest payload with category titles, article titles, summaries, and URLs, **When** it is submitted, **Then** the app stores it as the canonical digest for that date.
3. **Given** a digest already exists for a date, **When** a new payload is submitted for the same date, **Then** the app updates or replaces the existing digest deterministically.

---

### User Story 4 - Clean, Future-Oriented Public and Admin Visuals (Priority: P2)

As a product owner, I want the public digest and admin console to have a minimal but intentional "future-facing" visual style, so the app feels like a product rather than a raw ops page.

**Why this priority**: The public digest is a presentation surface; visual quality matters, but it must not block core routing/API separation.

**Independent Test**: Load the public digest and `/admin` on desktop/mobile and verify both render usable layouts with distinct visual intent and no broken navigation.

**Acceptance Scenarios**:

1. **Given** the public digest page, **When** it loads, **Then** it uses a digest-first layout optimized for reading grouped summaries.
2. **Given** the admin console, **When** it loads, **Then** it remains functional but visually distinct from the public digest.
3. **Given** mobile viewport widths, **When** either page loads, **Then** core controls and content remain readable and usable.

## Edge Cases

- Root route loads before any digest has ever been submitted.
- A digest exists for some dates but not for others.
- External client submits malformed group structure, missing summary text, or invalid URLs.
- External client submits duplicate digest entries inside the same group.
- The same article appears across multiple groups in one report.
- Public digest page is requested while storage is temporarily unavailable.
- Admin auth cookies are missing, expired, or invalid.
- Existing `/api/*` admin-only routes must remain protected while selected public digest routes stay open.
- A digest is regenerated later the same day and should replace the prior version cleanly.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST serve a public daily digest page at `/`.
- **FR-002**: System MUST default the public digest page to the current UTC date unless another date is explicitly requested.
- **FR-003**: System MUST allow the public digest page to load digest content for an explicitly selected date.
- **FR-004**: System MUST provide a public read API for retrieving the stored digest for a given date.
- **FR-005**: System MUST provide an app API that returns a list of article links and metadata for a requested date.
- **FR-006**: System MUST provide an app API that accepts a grouped digest submission for a requested date.
- **FR-007**: System MUST store digest reports durably in the application database.
- **FR-008**: System MUST support deterministic replacement or update of an existing digest for the same date.
- **FR-009**: System MUST expose admin/operator UI only under `/admin`.
- **FR-010**: System MUST require the existing password-based auth flow for `/admin` and protected admin APIs.
- **FR-011**: System MUST keep public digest routes accessible without admin authentication.
- **FR-012**: System MUST preserve existing admin capabilities inside `/admin` (update run/status, parsed news tools, source onboarding).
- **FR-013**: System SHOULD keep the external agent integration app-agnostic; OpenClaw/PocketPaw should behave as API clients rather than server-embedded dependencies.
- **FR-014**: System SHOULD render digest items as grouped sections with title, short summary, and source link only.
- **FR-015**: System SHOULD present the public digest with a minimal but intentional product-style design distinct from the admin console.
- **FR-016**: System MUST return a clean empty-state contract for missing digest dates instead of failing the public page render.
- **FR-017**: System MUST keep existing admin-only `/api/update/*` and `/api/source-onboarding/*` protections intact after routing changes.

### Key Entities *(include if feature involves data)*

- **NewsDigestReport**: Canonical digest for a specific date, including metadata about generation and last update.
- **NewsDigestGroup**: A titled section inside a digest (for example, "AI Coding", "Agent Platforms", "Security").
- **NewsDigestItem**: A single summarized news entry inside a digest group, containing title, short description, source link, and optional article/source references.
- **DigestLinkFeedItem**: API payload item representing a stored article link and its metadata for a target date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Unauthenticated visitors opening `/` can see the public digest page with no login prompt in **100%** of tested cases.
- **SC-002**: Unauthenticated visitors cannot access `/admin` operational tools without passing the existing login gate in **100%** of tested cases.
- **SC-003**: An external client can fetch a date-scoped link list and successfully submit a grouped digest for that date in one deterministic API flow.
- **SC-004**: The public digest page renders grouped digest content for a selected date with no admin controls exposed.
- **SC-005**: Existing admin update/onboarding flows continue to work after being moved under `/admin`.
- **SC-006**: The public digest page returns a stable empty-state for dates with no digest instead of returning a raw server error.
