# Tasks: MCP Agent Access and Full-Text Article Dataset

**Input**: Design documents from `/specs/003-mcp-agent-fulltext/`  
**Prerequisites**: plan.md (required), spec.md (required)

**Tests**: Include unit/e2e tests for changed ingestion and MCP tool behavior.

**Organization**: Tasks are grouped by user story to preserve independent delivery and verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no direct dependency)
- **[Story]**: Which user story this task belongs to (`US1`, `US2`, `US3`, `US4`)

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create feature docs artifacts (`plan.md`, `tasks.md`) in `specs/003-mcp-agent-fulltext/`
- [ ] T002 Add MCP package dependency in `pyproject.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T003 Add agent-query repository methods in `src/app/storage/repos.py` (`list_for_agent`, `get_article_for_agent`)
- [ ] T004 [P] Add RSS full-text extraction settings in `src/app/config/settings.py`
- [ ] T005 Add reusable plain-text normalization for RSS linked-page extraction in `src/app/ingest/rss.py`

**Checkpoint**: Foundation complete, user stories can be implemented.

---

## Phase 3: User Story 1 - Agent Triggers and Tracks Update Runs via MCP (Priority: P1) 🎯 MVP

**Goal**: Agent can start update and observe lifecycle/counters through MCP.

**Independent Test**: Start update via MCP tool, poll status until terminal state, validate counters and conflict handling.

### Tests for User Story 1

- [ ] T006 [P] [US1] Add MCP update/status unit tests in `tests/unit/test_mcp_server.py`

### Implementation for User Story 1

- [ ] T007 [US1] Implement MCP server skeleton and update/status tools in `src/app/mcp/server.py`
- [ ] T008 [US1] Add module export in `src/app/mcp/__init__.py`
- [ ] T009 [US1] Add CLI command to run MCP server in `src/app/cli/main.py`

---

## Phase 4: User Story 2 - Agent Reads Prepared Plain Text for Articles (Priority: P1)

**Goal**: Ingestion stores normalized plain text content, including RSS linked pages.

**Independent Test**: Feed items persist with `content` text where fetch/extraction succeeds; ingestion remains fail-soft when it does not.

### Tests for User Story 2

- [ ] T010 [P] [US2] Extend RSS ingestion tests for linked-page text extraction in `tests/unit/test_ingest_rss_additional.py`

### Implementation for User Story 2

- [ ] T011 [US2] Extend `fetch_rss` flow to enrich items with linked-page full text in `src/app/ingest/rss.py`
- [ ] T012 [US2] Wire RSS full-text controls into pipeline fetch call in `src/app/core/pipeline.py`

---

## Phase 5: User Story 3 - Agent Fetches Dataset Slices for Analysis (Priority: P1)

**Goal**: Agent can query list slices and fetch one article document via MCP tools.

**Independent Test**: List returns deterministic ordered subset; detail returns stored `content`.

### Tests for User Story 3

- [ ] T013 [P] [US3] Add MCP article list/detail tests in `tests/unit/test_mcp_server.py`

### Implementation for User Story 3

- [ ] T014 [US3] Implement MCP tools `news.list` and `news.get` in `src/app/mcp/server.py`
- [ ] T015 [US3] Implement deterministic list/detail repository usage in `src/app/storage/repos.py`

---

## Phase 6: User Story 4 - Safe and Controlled Agent Operations (Priority: P2)

**Goal**: Predictable validation, conflict responses, and structured errors for MCP operations.

**Independent Test**: Invalid MCP arguments and concurrent run starts return controlled errors.

### Tests for User Story 4

- [ ] T016 [P] [US4] Add invalid-input/conflict tests in `tests/unit/test_mcp_server.py`

### Implementation for User Story 4

- [ ] T017 [US4] Add typed input validation and structured error payloads in `src/app/mcp/server.py`
- [ ] T018 [US4] Ensure MCP operation logging mirrors existing structured logging conventions

---

## Phase 7: Polish & Cross-Cutting

- [ ] T019 [P] Update README with MCP usage and agent workflow commands in `README.md`
- [ ] T020 Run test suite (`pytest`) and lint (`ruff check .`) and fix regressions

---

## Dependencies & Execution Order

- Phase 1 -> Phase 2 -> US1/US2/US3 -> US4 -> Phase 7
- `US1` can start right after foundational tasks.
- `US2` should complete before validating `US3` content-heavy workflows.
- `US3` depends on repository methods from Phase 2 and MCP skeleton from US1.

## Parallel Opportunities

- T004 and T005 can run in parallel after T003 planning alignment.
- T006, T010, T013, T016 are parallel test tasks.
- T019 can run in parallel with final validation pass.

