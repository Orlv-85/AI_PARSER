# Implementation Plan: Weekly AI Analytics for Management Dashboard

**Branch**: `010-weekly-ai-analytics-for-management-dashboard` | **Date**: 2026-03-14 | **Spec**: `specs/010-weekly-ai-analytics-for-management-dashboard/spec.md`
**Input**: Approved intake and feature specification for weekly AI analytics

## Summary

Deliver a weekly management analytics flow that:
- derives a selected seven-day article set plus the immediately previous seven-day baseline,
- asks Antigravity to synthesize `summary/new/trending_up/trending_down`,
- validates the returned structure before exposing it,
- falls back to deterministic sections when Antigravity fails,
- and preserves the public web/API contract for the weekly analytics page.

## Technical Context

**Language/Version**: Python 3.14  
**Primary Dependencies**: FastAPI, SQLAlchemy, Pydantic, httpx, Typer  
**Storage**: SQLite for local/dev, PostgreSQL in production  
**Testing**: `./venv1/bin/pytest`, `./venv1/bin/python -m ruff check`  
**Target Platform**: Server-side Python web app on Linux/macOS  
**Project Type**: Single FastAPI application with storage and HTML templates  
**Performance Goals**: Weekly analytics page shell loads immediately; report generation tolerates up to 60 seconds for Antigravity  
**Constraints**: Do not break existing CLI/API/ingestion behavior; Antigravity dependency must fail safely; keep changes inside `specs/010`, `src/app`, `tests`, and `pyproject.toml`  
**Scale/Scope**: One public weekly analytics page and API route backed by existing article storage

## Constitution Check

- Small, testable slice: pass
- Existing CLI/API compatibility preserved: required and enforced by scope
- Closest tests read before edits: pass
- Spec/plan/tasks traceability recorded: required in this slice

## Project Structure

### Documentation

```text
specs/010-weekly-ai-analytics-for-management-dashboard/
├── execution_packet.md
├── plan.md
├── spec-intake.md
├── spec.md
└── tasks.md
```

### Source Code

```text
src/app/
├── config/settings.py
├── storage/repos.py
└── web/
    ├── app.py
    ├── models.py
    └── weekly_analytics.html

tests/unit/
├── test_news_digest_repo.py
└── test_web_weekly_analytics.py
```

**Structure Decision**: Keep the implementation inside the existing repository/storage/web layers. Weekly analytics generation logic belongs in `src/app/storage/repos.py`; API and page behavior remain in the established FastAPI web layer.

## Implementation Slices

### Slice A - Spec packet recovery and traceability

- Replace templated `spec.md`, `plan.md`, and `tasks.md` with intake-driven content.
- Record acceptance traceability from intake -> requirements -> tasks -> automated tests.

### Slice B - Weekly analytics generation through Antigravity

- Extend `WeeklyAnalyticsRepo.get_weekly_report()` to:
  - resolve the selected and prior seven-day windows,
  - collect recent/prior article rows,
  - attempt Antigravity generation with report metadata and selected rows,
  - validate the payload shape,
  - return validated Antigravity output or deterministic fallback.
- Keep fallback generation deterministic and fully local so the endpoint remains available when the external dependency is degraded.
- Log Antigravity failures and invalid payloads for operator visibility.

### Slice C - Contract verification

- Use the repo tests as the primary contract for selected-window generation, timeout fallback, and malformed-payload fallback.
- Preserve existing weekly analytics API contract already covered by web tests.

## Acceptance Traceability

| Requirement | Implementation | Tests |
|---|---|---|
| FR-001, FR-002 | `WeeklyAnalyticsRepo.get_weekly_report()` computes selected/prior seven-day windows | `tests/unit/test_news_digest_repo.py::test_weekly_report_uses_antigravity_output_for_selected_seven_day_window` |
| FR-003 | `_generate_antigravity_report()` receives `report_date`, `date_from`, `date_to`, `recent_rows`, `prior_rows` | `tests/unit/test_news_digest_repo.py::test_weekly_report_uses_antigravity_output_for_selected_seven_day_window` |
| FR-004 | Antigravity payload validation rejects malformed sections or items | `tests/unit/test_news_digest_repo.py::test_weekly_report_falls_back_when_antigravity_payload_is_invalid` |
| FR-005, FR-006 | deterministic fallback plus logging on timeout/error/invalid payload | `tests/unit/test_news_digest_repo.py::test_weekly_report_falls_back_when_antigravity_times_out`, `tests/unit/test_news_digest_repo.py::test_weekly_report_falls_back_when_antigravity_payload_is_invalid` |
| FR-007, FR-008 | existing weekly analytics page/API wiring remains intact | `tests/unit/test_web_weekly_analytics.py` |

## Validation Plan

Run the smallest useful checks for the changed slice:

- `./venv1/bin/python -m ruff check src/app/storage/repos.py tests/unit/test_news_digest_repo.py`
- `./venv1/bin/pytest tests/unit/test_news_digest_repo.py -q`

If the weekly analytics web contract is touched materially, also run:

- `./venv1/bin/pytest tests/unit/test_web_weekly_analytics.py -q`

## Risks

- Antigravity API contract is inferred locally because no existing client is present in the repo.
- External generation can fail for timeout, transport, or malformed content; fallback must remain the source of truth in those cases.
- Existing user changes are already present in weekly analytics files, so edits must stay narrowly scoped to avoid clobbering unrelated work.
