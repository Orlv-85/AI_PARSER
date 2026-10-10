# Feature Specification: Weekly AI Analytics for Management Dashboard

**Feature Branch**: `010-weekly-ai-analytics-for-management-dashboard`  
**Created**: 2026-03-14  
**Status**: Approved for implementation  
**Input**: Intake from `spec-intake.md`

## Context

Management stakeholders need a weekly AI market view, not just a stream of individual stories. The feature adds a public weekly analytics page and API that summarize the selected seven-day window through Antigravity while preserving the existing news, digest, and ingestion behavior.

## User Scenarios & Testing

### User Story 1 - Weekly management briefing from the latest 7 days (Priority: P1)

As a CEO, COO, CPO, or product lead, I can open a weekly analytics report for a selected date and see a management-oriented summary of the prior seven days of AI news.

**Why this priority**: This is the core business value called out in the intake and the minimum useful release.

**Independent Test**: Request the weekly analytics report for a known date and verify the response covers exactly the selected seven-day window and returns `summary`, `new`, `trending_up`, and `trending_down`.

**Acceptance Scenarios**:

1. **Given** AI news exists for the selected report week, **When** a weekly report is generated, **Then** the system sends the selected seven-day set and the immediately preceding seven-day baseline to Antigravity and returns the validated summary sections.
2. **Given** the report date is `2026-03-07`, **When** the weekly report is generated, **Then** the selected window is `2026-03-01` through `2026-03-07` inclusive.

### User Story 2 - Reliable fallback during Antigravity failure (Priority: P1)

As a management user, I still receive a coherent weekly report when Antigravity times out or returns malformed output.

**Why this priority**: The intake explicitly requires understandable error handling and the page must remain usable when the external dependency fails.

**Independent Test**: Force Antigravity generation to time out or return an invalid payload and verify the report falls back to deterministic sections derived from stored news.

**Acceptance Scenarios**:

1. **Given** Antigravity times out, **When** the weekly report is requested, **Then** the system logs the failure and returns the deterministic fallback summary and sections for the same selected window.
2. **Given** Antigravity returns a payload with missing or malformed sections, **When** the weekly report is requested, **Then** the system rejects the payload and returns the deterministic fallback report instead of partial data.

### User Story 3 - Discoverable weekly analytics entry point (Priority: P2)

As a management user, I can navigate from the main web page to the weekly analytics report without losing the selected report date.

**Why this priority**: The intake requires a new web UI section and navigation from the home page, but it depends on the report contract already working.

**Independent Test**: Open the main page for a selected date and verify the weekly analytics link and API-backed page preserve that date.

**Acceptance Scenarios**:

1. **Given** I am on the main page for a selected date, **When** I follow the weekly analytics link, **Then** the destination uses the same report date.

## Edge Cases

- No AI news exists in the selected seven-day window.
- The previous seven-day baseline has no overlapping topics.
- Antigravity is unavailable, times out, or returns non-JSON.
- Antigravity returns JSON that does not match the required `summary/new/trending_up/trending_down` structure.
- The weekly report request must not change the existing digest or article API contracts.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST build weekly analytics for an explicit `report_date` using the inclusive seven-day window ending on that date.
- **FR-002**: The system MUST compare the selected seven-day window against the immediately preceding seven-day window when deriving `new`, `trending_up`, and `trending_down`.
- **FR-003**: The system MUST pass the selected week, the prior baseline week, and the target report date into Antigravity generation.
- **FR-004**: The system MUST accept only Antigravity payloads that contain a non-empty `summary` string and list-valued `new`, `trending_up`, and `trending_down` sections whose items each contain `title`, `summary`, and `url`.
- **FR-005**: The system MUST fall back to the deterministic weekly analytics report when Antigravity times out, raises an error, or returns an invalid payload.
- **FR-006**: The system MUST log Antigravity request failures and payload validation failures without crashing the weekly analytics endpoint.
- **FR-007**: The web UI MUST expose a Weekly AI Analytics entry point from the main page and preserve the selected report date in navigation.
- **FR-008**: The feature MUST preserve existing CLI, API, ingestion, and digest behavior outside the new weekly analytics surface.

### Key Entities

- **Weekly Analytics Report**: A report keyed by `report_date` with `date_from`, `date_to`, a management `summary`, and three item lists: `new`, `trending_up`, and `trending_down`.
- **Weekly Analytics Item**: A report item containing `title`, `summary`, and `url`.
- **Selected Window Rows**: Top-ranked AI articles from the target seven-day range sent to Antigravity and used for deterministic fallback.
- **Prior Window Rows**: Top-ranked AI articles from the preceding seven-day baseline used for comparison and fallback section derivation.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Weekly analytics requests for a selected date always evaluate exactly seven calendar days ending on that date.
- **SC-002**: When Antigravity returns a valid payload, the API exposes all four management sections in the expected schema.
- **SC-003**: When Antigravity fails or returns malformed data, the system still returns a complete fallback report instead of an error page.
- **SC-004**: Acceptance criteria from the intake are traceable to requirements, planned tasks, and automated tests in the feature packet.

## Acceptance Traceability

| Intake acceptance | Requirements | Planned tasks | Validation |
|---|---|---|---|
| Main page links to Weekly AI Analytics | FR-007, FR-008 | T003, T008 | `tests/unit/test_web_weekly_analytics.py::test_public_digest_page_links_to_weekly_ai_analytics` |
| Report uses the latest selected 7 days | FR-001, FR-002, FR-003 | T001, T004, T005 | `tests/unit/test_news_digest_repo.py::test_weekly_report_uses_antigravity_output_for_selected_seven_day_window` |
| Report contains New / Trending Up / Trending Down and management summary | FR-004 | T001, T004, T005 | `tests/unit/test_news_digest_repo.py::test_weekly_report_uses_antigravity_output_for_selected_seven_day_window`, `tests/unit/test_web_weekly_analytics.py::test_weekly_ai_analytics_api_returns_report_sections_for_last_7_days` |
| Errors are handled clearly | FR-005, FR-006 | T002, T004, T006 | `tests/unit/test_news_digest_repo.py::test_weekly_report_falls_back_when_antigravity_times_out`, `tests/unit/test_news_digest_repo.py::test_weekly_report_falls_back_when_antigravity_payload_is_invalid` |
