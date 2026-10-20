# Implementation Plan: MCP Authentication and Access Control

**Branch**: `004-mcp-authentication` | **Date**: 2026-02-21 | **Spec**: `specs/015-mcp-authentication/spec.md`  
**Input**: Feature specification from `/specs/015-mcp-authentication/spec.md`

## Summary

Add authentication enforcement to MCP tool access with environment-driven configuration, startup validation, and structured auth audit logging. Keep compatibility for local development when MCP auth is disabled.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastMCP, FastAPI, Pydantic Settings, Typer  
**Storage**: N/A (auth config from env)  
**Testing**: pytest  
**Target Platform**: local/server process where MCP server runs  
**Project Type**: single backend service  
**Performance Goals**: minimal auth overhead (<50ms median local)  
**Constraints**: no secret leakage in logs, fail-fast config validation  
**Scale/Scope**: single-node MCP server with multiple agent clients

## Constitution Check

*GATE: Must pass before implementation.*

- Spec-first workflow: PASS (spec created)
- Security baseline: PASS (auth + logging requirements captured)
- Incremental delivery: PASS (can ship as MCP-only auth layer)
- Verifiability: PASS (explicit deny/allow test cases)

## Project Structure

### Documentation (this feature)

```text
specs/015-mcp-authentication/
├── spec.md
└── plan.md
```

### Source Code (repository root)

```text
src/app/
├── config/settings.py
├── mcp/server.py
├── observability/logging.py
└── cli/main.py

tests/
└── unit/
    ├── test_mcp_server.py
    └── test_settings.py
```

**Structure Decision**: Reuse existing MCP server module and settings layer; add auth checks in MCP call path.

## Implementation Strategy

1. Extend settings with MCP auth config and validation.
2. Add auth guard/middleware-like checks around MCP tool invocation.
3. Emit structured auth logs for success/failure without secret leakage.
4. Add unit tests for deny/allow and startup validation paths.
5. Update README with MCP auth setup and agent client usage.

## Risks & Mitigations

- FastMCP auth hook API differences: keep auth logic inside `MCPNewsService` call boundaries if needed.
- Misconfiguration in production: strict startup validation and clear error messages.
- Breaking existing local flow: explicit `AINEWS_MCP_AUTH_ENABLED=false` compatibility path.
