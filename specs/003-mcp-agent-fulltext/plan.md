# Implementation Plan: MCP Agent Access and Full-Text Article Dataset

**Branch**: `003-mcp-agent-fulltext` | **Date**: 2026-02-21 | **Spec**: `specs/003-mcp-agent-fulltext/spec.md`  
**Input**: Feature specification from `/specs/003-mcp-agent-fulltext/spec.md`

## Summary

Add an agent-oriented MCP interface (FastMCP) on top of the existing ingest/query pipeline and ensure articles are persisted with normalized plain text content (including RSS linked-page extraction). Reuse current update-run orchestration and storage repositories to minimize regression risk.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, SQLAlchemy, Typer, httpx, feedparser, trafilatura/readability-lxml, FastMCP  
**Storage**: SQLite/PostgreSQL via existing SQLAlchemy models  
**Testing**: pytest  
**Target Platform**: Linux/macOS server process  
**Project Type**: single backend service (CLI + web + MCP)  
**Performance Goals**: MCP run trigger response <2s; list query <2s for first 100 records on 100k dataset  
**Constraints**: Fail-soft ingestion, deterministic ordering, no concurrent conflicting update runs  
**Scale/Scope**: 20-100 sources, daily recurring fetch cycles, agent-driven post-analysis workflows

## Constitution Check

*GATE: Must pass before implementation.*

- Spec-first workflow: PASS (spec exists for feature 003)
- Reliability and observability: PASS (explicit logging + fail-soft preserved in requirements)
- Incremental delivery: PASS (tasks are story-grouped and independently testable)
- Test coverage for changed behavior: PASS (unit/e2e tasks included below)

## Project Structure

### Documentation (this feature)

```text
specs/003-mcp-agent-fulltext/
├── spec.md
├── plan.md
└── tasks.md
```

### Source Code (repository root)

```text
src/app/
├── cli/main.py
├── config/settings.py
├── core/pipeline.py
├── ingest/rss.py
├── mcp/
│   ├── __init__.py
│   └── server.py
├── storage/repos.py
└── web/service.py

tests/
├── unit/
│   ├── test_ingest_rss_additional.py
│   ├── test_mcp_server.py
│   └── test_storage_extra.py
└── e2e/
    └── test_api_e2e.py
```

**Structure Decision**: Keep single-project layout and add a dedicated `src/app/mcp` module that reuses existing service/repository layers.

## Implementation Strategy

1. Add foundational plumbing for MCP module and agent-friendly storage reads.
2. Extend RSS ingestion to attempt linked-page text extraction into `content`.
3. Expose update/status/list/detail operations as FastMCP tools.
4. Add CLI entrypoint for MCP server startup.
5. Add targeted tests and run regression suite.

## Risks & Mitigations

- FastMCP API compatibility risk: isolate MCP integration in `src/app/mcp/server.py`.
- Source-side scraping variance: keep per-item fail-soft and whitespace normalization.
- Latency growth from RSS full-text fetch: add bounded extraction controls in settings.

