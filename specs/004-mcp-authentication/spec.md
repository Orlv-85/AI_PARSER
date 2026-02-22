# Feature Specification: MCP Authentication and Access Control

**Feature Branch**: `004-mcp-authentication`  
**Created**: 2026-02-21  
**Status**: Draft  
**Input**: User description: "нужна авторизация для mcp, чтобы агенты подключались безопасно"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent Authenticates to MCP Before Tool Access (Priority: P1)

As an agent client, I must provide valid credentials/token to use MCP tools.

**Why this priority**: Without auth, MCP is open to any process/network actor with access to endpoint.

**Independent Test**: Attempt MCP tool call without token and with invalid token (expect deny), then with valid token (expect success).

**Acceptance Scenarios**:

1. **Given** MCP auth is enabled, **When** client calls `news.list` without credentials, **Then** request is denied with auth error.
2. **Given** MCP auth is enabled, **When** client calls MCP with valid credential, **Then** call succeeds according to tool logic.

---

### User Story 2 - Operator Configures MCP Auth via Environment (Priority: P1)

As an operator, I can configure MCP auth settings (enabled flag, token secret/keys, mode) without code edits.

**Why this priority**: Production setup must be controlled through deployment config, not source changes.

**Independent Test**: Set env vars, start MCP server, verify behavior reflects configuration.

**Acceptance Scenarios**:

1. **Given** auth env vars are set, **When** service starts, **Then** MCP auth mode is active and enforced.
2. **Given** required auth vars are missing while auth is enabled, **When** service starts, **Then** startup fails fast with clear config error.

---

### User Story 3 - Access Is Auditable (Priority: P2)

As an operator, I can inspect structured logs for MCP auth successes/failures and tool access outcomes.

**Why this priority**: Security controls are incomplete without audit trail.

**Independent Test**: Perform authorized and unauthorized MCP calls and verify structured log events.

**Acceptance Scenarios**:

1. **Given** invalid credential attempts, **When** calls are made, **Then** logs contain auth-failure events without leaking secrets.
2. **Given** valid tool calls, **When** calls complete, **Then** logs include auth-success/access context.

### Edge Cases

- Missing token header/field.
- Expired or malformed token.
- Clock skew for time-based token validation [NEEDS CLARIFICATION].
- Multiple agents sharing one token vs per-agent tokens [NEEDS CLARIFICATION].
- Backward compatibility when auth is disabled in local/dev.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support MCP authentication when enabled via configuration.
- **FR-002**: System MUST reject unauthenticated MCP tool calls when MCP auth is enabled.
- **FR-003**: System MUST reject invalid credentials with explicit auth error response.
- **FR-004**: System MUST allow valid authenticated clients to execute MCP tools unchanged.
- **FR-005**: System MUST provide configuration via environment variables for MCP auth enablement and credential material.
- **FR-006**: System MUST fail startup when MCP auth is enabled but required auth settings are missing/invalid.
- **FR-007**: System MUST log auth events (`mcp_auth_success`, `mcp_auth_failed`) without exposing raw credentials/secrets.
- **FR-008**: System MUST preserve existing local developer flow when MCP auth is explicitly disabled.
- **FR-009**: System MUST document MCP auth setup and client usage in README.

### Non-Functional / Security Requirements

- **NFR-001**: Auth verification overhead SHOULD add no more than 50ms median per MCP request in local environment.
- **NFR-002**: Credential secrets MUST never be written to logs.
- **NFR-003**: Default production recommendation MUST be auth enabled.

### Key Entities *(include if feature involves data)*

- **MCPAuthConfig**: runtime auth settings (`enabled`, mode, secret/token source).
- **MCPAuthContext**: per-request auth result (`subject`, `auth_mode`, `is_authenticated`).
- **MCPAuthEvent**: structured log payload for auth decisions and failures.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of MCP tool calls without valid credentials are denied when auth is enabled.
- **SC-002**: 100% of valid authenticated MCP calls succeed subject to tool logic.
- **SC-003**: 100% of auth failures and successes emit structured log events without secret leakage.
- **SC-004**: Startup validation catches 100% of misconfigured required auth settings when auth is enabled.
