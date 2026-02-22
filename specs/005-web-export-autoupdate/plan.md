# Plan: Web Article Details, Export, and Scheduled Auto-Update

## Scope

Implement spec `005-web-export-autoupdate` in one slice with tests-first execution using nested agents (tester/generator/reviewer).

## Tasks

### T1. Web article details endpoint

- Add response model for article details payload.
- Add route `GET /api/news/{article_id}` in `src/app/web/app.py`.
- Reuse `ArticleRepo.get_article_for_agent()` to avoid duplicate query logic.
- Add unit tests for:
  - success response,
  - not found (`404`),
  - auth behavior unaffected (existing auth tests may remain unchanged if route falls under middleware automatically).

### T2. Web export endpoint (JSON)

- Add export response generation using existing `list_for_view()` filtering semantics.
- Add `include_content` query parameter.
- Return `JSONResponse` with attachment header.
- Add unit tests for:
  - JSON shape / attachment header,
  - filter passthrough,
  - `include_content=false` excludes heavy fields,
  - `include_content=true` includes `summary`, `content`, `url`.

### T3. Date range filtering for web/API

- Extend `/api/news` query params with optional `date_from` and `date_to`.
- Extend `/api/news/export` to support the same date range params.
- Update repository query logic (or add a wrapper) so explicit date range overrides relative `hours`.
- Update web UI controls (date inputs) and request serialization.
- Add tests for:
  - `date_from/date_to` passthrough,
  - single-day filtering (`date_from == date_to`),
  - backward compatibility when date range is omitted.

### T4. Web UI copy visible links to clipboard

- Add a UI button to copy URLs for currently displayed items.
- Use `navigator.clipboard.writeText(...)` with fallback/error messaging.
- Ensure copied output is one URL per line and reflects current filters/sort.
- Add lightweight frontend/unit test coverage if feasible; otherwise manual verification notes.

### T5. Cron-friendly auto-update script + docs

- Add `scripts/auto_update_once.sh`:
  - shell-safe (`set -euo pipefail`)
  - forwards env vars
  - runs `ai-news fetch --once` (local venv or docker-compose command choice documented)
- Update `README.md` with:
  - recommended envs (`20/8`)
  - `cron` example every 30 minutes
  - overlap caution
- Add minimal script syntax check (if existing test coverage for scripts is not practical).

## Implementation Notes

- No scheduler inside FastAPI app in this iteration.
- Keep `/api/news` existing response unchanged (backward compatible).
- Export endpoint should reuse existing query parameters for consistency.
- For large exports, JSON streaming is deferred; regular JSON response is acceptable in this scope.

## Multi-Agent TDD Execution (after approval)

1. Tester agent:
   - Add/extend web API/unit tests for T1 + T2 + T3 (and UI tests if feasible).
   - Write handoff to `tmp/tester_out.md`.
2. Generator agent:
   - Implement T1 + T2 + T3 + T4 + T5.
   - Run targeted tests and `make lint`.
   - Write handoff to `tmp/generator_out.md`.
3. Reviewer agent:
   - Validate against spec/plan and check for regressions.
   - Write `tmp/reviewer_out.md` and `tmp/agent_audit.txt`.
4. Orchestrator:
   - Run independent checks (targeted tests / lint / diff review).

## File Scope (expected)

- `src/app/web/app.py`
- `src/app/web/models.py`
- `src/app/web/index.html`
- `tests/unit/test_web_app.py`
- `tests/unit/test_storage_extra.py` (optional if query helpers are introduced)
- `scripts/auto_update_once.sh`
- `README.md`
- (optional) small helper additions in storage/web layers only if needed

## Approval Gate

Do not start implementation until user explicitly approves this spec + plan.
