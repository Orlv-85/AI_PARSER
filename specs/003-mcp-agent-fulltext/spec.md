# Feature Specification: MCP Agent Access and Full-Text Article Dataset

**Feature Branch**: `003-mcp-agent-fulltext`  
**Created**: 2026-02-21  
**Status**: Draft  
**Input**: User description: "хочу чтобы этим приложением пользовались агенты... не просто линки парсить а весь текст статьи... хочу mcp чтобы агенты подключались... могли обновление запустить, дождаться результата, собрать данные и анализировать"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent Triggers and Tracks Update Runs via MCP (Priority: P1)

As an AI agent, I can start a data update run through MCP and poll/wait for completion status to know when a dataset is ready.

**Why this priority**: Without remote run control and status tracking, agents cannot reliably orchestrate ingestion workflows.

**Independent Test**: Connect MCP client, call update tool, wait for terminal status, and verify run counters are returned.

**Acceptance Scenarios**:

1. **Given** MCP server is available and no active run exists, **When** agent calls `news.update`, **Then** system starts exactly one run and returns `run_id` with `running` status.
2. **Given** a run is active, **When** agent requests status via MCP, **Then** system returns current state and transitions to `finished` or `failed` with counters (`fetched`, `new`, `duplicates`, `errors`).

---

### User Story 2 - Agent Reads Prepared Plain Text for Articles (Priority: P1)

As an AI agent, I can retrieve articles that include cleaned plain text content, so I can analyze without visiting source pages.

**Why this priority**: Core value is agent-ready text corpus, not just links/metadata.

**Independent Test**: Run update, request articles via MCP/API, and verify records contain URL + normalized plain text body (without HTML markup).

**Acceptance Scenarios**:

1. **Given** an article page can be fetched and parsed, **When** ingestion completes, **Then** article is stored with plain text in `content`.
2. **Given** extraction fails for some source item, **When** ingestion completes, **Then** article metadata is still stored and failure is logged without aborting whole run.

---

### User Story 3 - Agent Fetches Dataset Slices for Analysis (Priority: P1)

As an AI agent, I can query prepared article datasets (filters/limits/time windows) and fetch full text for selected items.

**Why this priority**: Enables scalable analysis loops where agents process only relevant subsets.

**Independent Test**: Query by recency/relevance/source, retrieve article list, then fetch full text payloads for selected IDs.

**Acceptance Scenarios**:

1. **Given** stored articles exist, **When** agent calls list/query MCP tool with filters, **Then** system returns deterministic ordered subset with IDs and metadata.
2. **Given** agent requests article details by ID, **When** record exists, **Then** response includes plain text content and canonical metadata.

---

### User Story 4 - Safe and Controlled Agent Operations (Priority: P2)

As an operator, I can ensure agent-triggered updates/reads are controlled with clear errors, auth boundaries, and no conflicting concurrent runs.

**Why this priority**: Production safety is critical but secondary to core MCP data flow.

**Independent Test**: Attempt concurrent run start, invalid tool input, and unauthorized access; verify predictable rejection behavior.

**Acceptance Scenarios**:

1. **Given** one update run is active, **When** second `news.update` is called, **Then** system rejects with explicit conflict response.
2. **Given** invalid MCP input (negative limits, invalid IDs), **When** tool is called, **Then** system returns validation error without internal crash.

### Edge Cases

- RSS entry exists but source page blocks scraping or times out.
- Article parsing yields boilerplate/empty text after cleanup.
- Source content is duplicated across multiple URLs with different tracking params.
- Very long articles exceed token budget for downstream analysis.
- MCP client disconnects while waiting for a long-running update status.
- Repeated update triggers arrive concurrently from multiple agents.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose MCP tools (FastMCP-based server) for agent operations: update run trigger, run status read, article list/query, article detail retrieval.
- **FR-002**: System MUST allow an agent to start an update run and receive a stable `run_id`.
- **FR-003**: System MUST expose run status states (`idle`, `running`, `finished`, `failed`) and counters (`fetched`, `new`, `duplicates`, `errors`) via MCP.
- **FR-004**: System MUST prevent conflicting concurrent update runs and return explicit conflict result for rejected start attempts.
- **FR-005**: System MUST persist article plain text (`content`) as normalized text without HTML tags/markup when extraction succeeds.
- **FR-006**: System MUST keep existing article metadata persistence (title, canonical URL, source, published time, scores) even when text extraction is unavailable.
- **FR-007**: System MUST perform full-text extraction for HTML sources and MUST attempt article-page extraction for RSS items that provide only feed snippets/links.
- **FR-008**: System MUST support agent dataset retrieval with filters at minimum by recency window, limit, optional search query, and relevance threshold.
- **FR-009**: System MUST support retrieving one article payload by ID including full plain text content for downstream LLM analysis.
- **FR-010**: System MUST return deterministic ordering for list/query responses (`rank_score DESC`, then `published_at DESC` unless alternate sort explicitly requested).
- **FR-011**: System MUST log MCP-triggered runs and data access operations with request context while excluding sensitive credentials.
- **FR-012**: System MUST provide clear, structured validation errors for invalid MCP inputs.
- **FR-013**: System MUST keep ingestion fail-soft: per-item extraction failures MUST NOT fail the whole source or whole run.

### Non-Functional Requirements

- **NFR-001**: End-to-end update trigger acknowledgement via MCP SHOULD return within 2 seconds in normal conditions.
- **NFR-002**: Article query endpoint/tool SHOULD return first 100 filtered records in under 2 seconds on SQLite dataset up to 100,000 rows on a single host.
- **NFR-003**: Full-text storage format MUST be UTF-8 plain text with whitespace normalization to reduce downstream token waste.
- **NFR-004**: MCP server MUST support authenticated deployment mode consistent with existing web/API auth policy [NEEDS CLARIFICATION: shared auth/session model vs dedicated MCP token].

### Key Entities *(include if feature involves data)*

- **MCPUpdateRun**: Agent-visible run record (`run_id`, status, timestamps, counters, error message).
- **AgentArticleListItem**: Lightweight dataset row (`article_id`, title, source, published_at, rank_score, url_canonical, has_content).
- **AgentArticleDocument**: Full article payload for analysis (`article_id`, metadata, plain `content`, optional summary).
- **MCPQueryOptions**: Filter/sort controls (`hours/days`, `limit`, `min_ai_relevance`, `query`, `sort`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of successful MCP-triggered updates produce a terminal status with counters accessible by `run_id`.
- **SC-002**: At least 90% of newly ingested items from supported sources contain non-empty normalized plain text in `content` (excluding hard paywalls/blocked pages).
- **SC-003**: 100% of article detail MCP responses for existing IDs include stable metadata and return `content` exactly as stored (no on-demand refetch required).
- **SC-004**: Concurrent run-start conflict handling is deterministic: second start attempt is rejected 100% of the time while one run is active.
- **SC-005**: Agents can complete the workflow "start update -> wait for finished -> query dataset -> fetch documents" without manual CLI/web steps.
