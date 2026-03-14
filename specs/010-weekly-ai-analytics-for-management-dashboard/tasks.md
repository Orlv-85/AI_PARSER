# Tasks: Weekly AI Analytics for Management Dashboard

**Input**: `spec.md`, `plan.md`, `spec-intake.md`, `execution_packet.md`
**Prerequisites**: approved spec and plan, tester handoff in `tmp/tester_out.json`
**Tests**: This feature requires automated tests for the weekly analytics repo contract and fallback behavior.

## Traceability Map

| Task | Requirements | Acceptance |
|---|---|---|
| T001 | FR-001, FR-002, FR-003 | Selected report uses the explicit 7-day window and prior baseline |
| T002 | FR-004, FR-005, FR-006 | Invalid or failed Antigravity output falls back cleanly |
| T003 | FR-007, FR-008 | Main page entry point remains intact |
| T004 | FR-003, FR-004 | Antigravity contract produces management summary plus section lists |
| T005 | FR-005, FR-006 | Timeout fallback remains deterministic |
| T006 | FR-005, FR-006 | Malformed-payload fallback remains deterministic |
| T007 | SC-004 | Spec packet includes acceptance traceability |
| T008 | FR-007 | Weekly analytics API/page contract remains stable |

## Phase 1: Spec Recovery

- [x] T007 Update `specs/010-weekly-ai-analytics-for-management-dashboard/spec.md`, `specs/010-weekly-ai-analytics-for-management-dashboard/plan.md`, and `specs/010-weekly-ai-analytics-for-management-dashboard/tasks.md` from intake and add acceptance traceability.

## Phase 2: User Story 1 - Weekly management briefing (Priority: P1)

**Goal**: Generate a weekly analytics report for the selected seven-day window and expose the expected management sections.

**Independent Test**: `tests/unit/test_news_digest_repo.py::test_weekly_report_uses_antigravity_output_for_selected_seven_day_window`

### Tests for User Story 1

- [x] T004 [US1] Maintain the Antigravity integration contract test in `tests/unit/test_news_digest_repo.py`.

### Implementation for User Story 1

- [x] T001 [US1] Update `src/app/storage/repos.py` so `WeeklyAnalyticsRepo.get_weekly_report()` computes the selected and prior seven-day windows and passes them to Antigravity generation.
- [x] T003 [US1] Preserve the existing weekly analytics page and API entry points in `src/app/web/app.py` and related models/templates.

## Phase 3: User Story 2 - Reliable fallback during Antigravity failure (Priority: P1)

**Goal**: Keep weekly analytics usable when Antigravity times out, errors, or returns malformed data.

**Independent Test**: Run the timeout and malformed-payload repo tests and verify deterministic fallback content is returned.

### Tests for User Story 2

- [x] T005 [US2] Maintain `tests/unit/test_news_digest_repo.py::test_weekly_report_falls_back_when_antigravity_times_out`.
- [x] T006 [US2] Maintain `tests/unit/test_news_digest_repo.py::test_weekly_report_falls_back_when_antigravity_payload_is_invalid`.

### Implementation for User Story 2

- [x] T002 [US2] Add Antigravity payload validation, timeout/error handling, and fallback logging in `src/app/storage/repos.py`.

## Phase 4: User Story 3 - Discoverable weekly analytics navigation (Priority: P2)

**Goal**: Keep the Weekly AI Analytics destination reachable from the main page with the selected date preserved.

**Independent Test**: `tests/unit/test_web_weekly_analytics.py::test_public_digest_page_links_to_weekly_ai_analytics`

### Tests for User Story 3

- [x] T008 [US3] Preserve the weekly analytics web/API contract in `tests/unit/test_web_weekly_analytics.py`.

## Validation

- [x] V001 Run `./venv1/bin/python -m ruff check src/app/storage/repos.py tests/unit/test_news_digest_repo.py`
- [x] V002 Run `./venv1/bin/pytest tests/unit/test_news_digest_repo.py -q`
- [x] V003 Run `./venv1/bin/pytest tests/unit/test_web_weekly_analytics.py -q` if weekly analytics web wiring changes during implementation
