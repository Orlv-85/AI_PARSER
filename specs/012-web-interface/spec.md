# Feature Specification: Web Interface for News Operations

**Feature Branch**: `001-web-interface`  
**Created**: 2026-02-21  
**Status**: Draft  
**Input**: User description: "хочу чтобы была веб интерфейс. и там можно было бы выполнять обновление источников. и также просматривать новости,. которые спарсилисиь. отдельно обновление. и чтобы можно было настроить параметры обновления. и отдельно страница для просмотра.слева панель с кнопками. одна обновление. вторая просмотр."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Manual Update Run from Web UI (Priority: P1)

As an operator, I can open a dedicated "Update" page in the web UI and start a news update run manually.

**Why this priority**: Core value is controlling ingestion without CLI access. Without this flow, the feature does not solve the main user request.

**Independent Test**: Can be fully tested by opening the web UI, clicking "Update" in left sidebar, starting update, and seeing run status/result counters.

**Acceptance Scenarios**:

1. **Given** the app is running and sources are configured, **When** the operator opens the "Update" page and starts update, **Then** a new fetch run starts and its status is shown in UI.
2. **Given** an update run has finished, **When** the operator views run result, **Then** UI shows counters (`fetched`, `new`, `duplicates`, `errors`) and finish status.

---

### User Story 2 - Configure Update Parameters in Web UI (Priority: P1)

As an operator, I can configure update parameters from the "Update" page (timeouts/retries/rate-limit/concurrency) and apply them before running update.

**Why this priority**: User explicitly asked for configurable update parameters; without this, manual update is incomplete.

**Independent Test**: Can be fully tested by changing parameters in UI, saving them, running update, and verifying run uses new values.

**Acceptance Scenarios**:

1. **Given** default update settings, **When** operator changes retry count and timeout and saves, **Then** settings are persisted and displayed as active.
2. **Given** updated parameters were saved, **When** operator starts new update run, **Then** run executes with saved parameters.

---

### User Story 3 - Browse Parsed News on Separate Page (Priority: P1)

As a reader/operator, I can open a dedicated "View" page and browse parsed news items from storage.

**Why this priority**: Viewing parsed results is the second key request and must be independent from update actions.

**Independent Test**: Can be fully tested by opening "View" page and confirming list is loaded from DB with title, date, rank, source, and canonical URL.

**Acceptance Scenarios**:

1. **Given** database has parsed articles, **When** operator opens "View" page, **Then** articles are shown in descending rank/date order.
2. **Given** there are no articles, **When** operator opens "View" page, **Then** empty state message is shown with no errors.

---

### User Story 4 - Left Sidebar Navigation (Priority: P2)

As a user, I can switch between "Update" and "View" pages using left sidebar buttons.

**Why this priority**: Required UX structure from request; navigation is needed for practical use but secondary to core data operations.

**Independent Test**: Can be fully tested by opening web app and switching pages via sidebar buttons.

**Acceptance Scenarios**:

1. **Given** web app is open, **When** user clicks "Update" button in left sidebar, **Then** update page becomes active.
2. **Given** web app is open, **When** user clicks "View" button in left sidebar, **Then** view page becomes active.

### Edge Cases

- What happens when user starts update while another update is already running?
- How does UI behave when source loading fails (invalid `sources.yaml` or missing file)?
- How does settings form validate out-of-range values (e.g., retries < 0, timeout = 0)?
- What happens when database is unavailable during view-page query?
- How should long-running update be shown (progress indicator, polling interval, timeout message)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a web interface served by the application process.
- **FR-002**: System MUST provide a persistent left sidebar with exactly two primary navigation actions: `Update` and `View`.
- **FR-003**: System MUST provide an `Update` page where the user can manually trigger a fetch/update run.
- **FR-004**: System MUST show update run status and final counters (`fetched`, `new`, `duplicates`, `errors`) on the `Update` page.
- **FR-005**: System MUST provide editable update parameters on `Update` page, including at minimum: `request_timeout_seconds`, `max_retries`, `per_source_min_interval_seconds`, `concurrency_limit`.
- **FR-006**: System MUST validate update parameters before save and reject invalid values with clear inline errors.
- **FR-007**: System MUST persist saved update parameters so they are reused for next update runs and restored after restart.
- **FR-008**: System MUST provide a `View` page that reads parsed news from storage and displays list items with: title, source, published_at, rank_score, canonical URL.
- **FR-009**: System MUST allow basic filtering/sorting on `View` page by recency window and result limit, matching existing CLI capabilities.
- **FR-010**: System MUST show explicit empty and error states on both pages (no data / backend error / validation error).
- **FR-011**: System MUST prevent concurrent conflicting update runs [NEEDS CLARIFICATION: reject second run vs queue it].
- **FR-012**: System MUST log web-triggered update actions in structured logs with run_id/source_id context where applicable.

### Key Entities *(include if feature involves data)*

- **WebUpdateSettings**: User-configurable runtime update parameters (timeout, retries, rate-limit, concurrency, last_updated_at).
- **FetchRunView**: Run metadata for UI display (run_id, started_at, finished_at, status, counters, error summary).
- **NewsListItem**: Read-model of stored article for view page (id, title, source_name/source_key, published_at, rank_score, url_canonical).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of update runs that are manually triggered from UI appear on screen with terminal status (`finished` or `failed`) within 2 seconds after completion.
- **SC-002**: 100% of valid update-parameter changes are persisted and applied to the next manual run.
- **SC-003**: `View` page initial load returns and renders first page of results in under 2 seconds for dataset up to 10,000 articles on local SQLite.
- **SC-004**: At least 95% of user navigation actions between `Update` and `View` complete without full page reload errors.
