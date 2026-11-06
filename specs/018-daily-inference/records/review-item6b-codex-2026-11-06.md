# Review (Codex gpt-6-astra high): PR #217, item 6b (2026-11-06)

Prompt: `prompt-item6b-review-codex-2026-11-06.md`. Saved by the coordinator.

**Verdict: changes needed.** Requested tests: **108 passed, 6 warnings**.

1. **P2 — Counter writes can block the public page.** [pages.py:164](src/app/web/routes/pages.py:164): counting completes before the response returns. An open PostgreSQL transaction locking today’s counter row can stall every `/` request, including with the switch off. No counter timeout is configured; exception handling cannot bound the wait. Isolate delivery from counting and bound database waits.

2. **P2 — Counter-table failures can still produce 503.** [pages.py:133](src/app/web/routes/pages.py:133): `create_all()` includes `page_views` before rendering. If that table is missing and creation fails—for example, denied PostgreSQL DDL or locked SQLite—the readable digest returns 503 before `_count_page` handles anything. The missing-table test masks this by replacing `create_all` with a no-op. Keep counter initialization outside the page’s required storage path.

3. **P2 — Switch-off OpenAPI compatibility changes.** [pages.py:177](src/app/web/routes/pages.py:177): changing the query annotation from `date | None` to `str | None` removes `format: date` from `/`’s OpenAPI parameter. Regenerated clients see a different contract even with the switch off. Preserve the schema and add a compatibility assertion.

Minor notes:

- Upserts are atomic, sessions close on failures, migration/model agree with one head, privacy fields are correct, and Compose defaults false. Live PostgreSQL was not tested.
- Switched rendering preserves escaping, HTTP(S) source-link filtering and diagnostic isolation. Existing test edits are justified; referenced test functions exist.
- `create_all()` follows existing practice, but weakens the documented counter-failure guarantee. Deployment starts the app before running Alembic.
- **CRAP:** the diff replaces three nested decision points with three, so router complexity did not increase. A numerical CRAP regression lacks baseline coverage evidence. Nevertheless, **32.9 exceeds the required <10**; a focused extraction of branching handlers is warranted now.

No files changed.
Coordinator: findings 1, 3 and the CRAP note fixed by `prompt-item6b-fixes-codex-2026-11-06.md`; finding 2 kept as decided (create_all as on every page; idempotent migration), recorded in pages.md Decisions.
