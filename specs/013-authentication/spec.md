# Feature Specification: Web Authentication and Access Control

**Feature Branch**: `002-authentication`  
**Created**: 2026-02-21  
**Status**: Draft  
**Input**: User description: "нужно сделать авторизацию"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Login Required for Web UI (Priority: P1)

As an operator, I must authenticate before I can access update/view pages and API endpoints.

**Why this priority**: Without auth, production deployment is unsafe and cannot be exposed on the internet.

**Independent Test**: Open app in browser without session and verify redirect/401, then login and verify access.

**Acceptance Scenarios**:

1. **Given** unauthenticated user opens `/`, **When** auth is enabled, **Then** user is redirected to login page.
2. **Given** unauthenticated user calls protected API endpoint, **When** request has no valid session, **Then** API returns `401 Unauthorized`.

---

### User Story 2 - Successful Login Creates Session (Priority: P1)

As an operator, I can sign in with valid credentials and get a secure authenticated session.

**Why this priority**: Core functional requirement for authorized access.

**Independent Test**: Submit valid credentials via login form, verify access to protected pages and endpoints without re-login during session lifetime.

**Acceptance Scenarios**:

1. **Given** valid username/password, **When** user submits login form, **Then** server sets session cookie and redirects to update page.
2. **Given** active valid session, **When** user opens protected pages, **Then** access is granted.

---

### User Story 3 - Failed Login and Logout (Priority: P1)

As an operator, I receive explicit error on invalid credentials and can log out to invalidate my session.

**Why this priority**: Required for safe operator flow and predictable security behavior.

**Independent Test**: Attempt invalid login and verify error; perform logout and verify protected resources are denied.

**Acceptance Scenarios**:

1. **Given** invalid credentials, **When** login is submitted, **Then** user stays on login page with generic auth error.
2. **Given** authenticated session, **When** user clicks logout, **Then** session is invalidated and next protected request is denied.

---

### User Story 4 - Session Expiration and Rotation (Priority: P2)

As an operator, session expires after configured TTL, and new login creates a new session token.

**Why this priority**: Reduces risk of stale long-lived sessions.

**Independent Test**: Set short TTL in test config and verify expired session is rejected; verify re-login issues new cookie/session id.

**Acceptance Scenarios**:

1. **Given** session exceeded TTL, **When** user requests protected endpoint, **Then** access is denied and login is required.
2. **Given** user logs in again, **When** session is recreated, **Then** previous session token is no longer valid.

### Edge Cases

- Auth disabled in local/dev mode should preserve current DX (no login barrier) [NEEDS CLARIFICATION].
- Brute-force login attempts should be rate-limited [NEEDS CLARIFICATION: strict requirement now vs later].
- Concurrent browser tabs after logout should all become unauthorized.
- API requests with expired or tampered cookie must return `401` consistently.
- Handling first-time deploy with no configured credentials [fail fast at startup vs auto-generate temporary creds].

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide username/password authentication for web access.
- **FR-002**: System MUST protect all web API endpoints under `/api/*` and pages `Update/View` when auth is enabled.
- **FR-003**: System MUST provide a login page and login API endpoint.
- **FR-004**: System MUST provide logout endpoint and invalidate active session on logout.
- **FR-005**: System MUST store only password hashes (no plaintext password persistence).
- **FR-006**: System MUST use secure signed session cookie (`HttpOnly`, `SameSite=Lax`, `Secure` in production).
- **FR-007**: System MUST support configurable session TTL via environment variable.
- **FR-008**: System MUST return `401` for unauthorized API requests and avoid leaking whether username or password was wrong.
- **FR-009**: System MUST expose startup validation for required auth secrets/credentials in production mode.
- **FR-010**: System MUST log authentication events (`login_success`, `login_failed`, `logout`, `session_expired`) without sensitive data.
- **FR-011**: System MUST support deployment-safe credential configuration via env vars or secret files.
- **FR-012**: System MUST include automated tests for successful login, failed login, protected route denial, logout, and session expiry.

### Non-Functional / Security Requirements

- **NFR-001**: Password hashing MUST use modern adaptive hash (Argon2id preferred; bcrypt acceptable fallback).
- **NFR-002**: Session signing secret MUST be at least 32 bytes of entropy.
- **NFR-003**: Authentication checks MUST add no more than 50ms median latency per protected request on local test environment.

### Key Entities *(include if feature involves data)*

- **AuthConfig**: runtime auth configuration (`enabled`, session TTL, cookie settings, secret source).
- **UserCredential**: credential material source (`username`, `password_hash`).
- **AuthSession**: authenticated browser session (`session_id`, `subject`, `issued_at`, `expires_at`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of protected endpoints reject unauthenticated requests with `401`.
- **SC-002**: 100% of valid login attempts create usable session, and 100% of invalid attempts are denied.
- **SC-003**: 100% of logout actions invalidate current session immediately.
- **SC-004**: Automated test suite includes auth e2e flow and passes in Docker CI.
- **SC-005**: No plaintext passwords or session secrets appear in logs or repository files.

## Implementation Notes (For Planning)

- Recommended first iteration: single-operator auth via env-based credentials (`AINEWS_AUTH_USERNAME`, `AINEWS_AUTH_PASSWORD_HASH`, `AINEWS_AUTH_SECRET`).
- Keep existing API unchanged for authenticated users to minimize regression risk.
- Add future extension point for multi-user/RBAC without breaking session format.
