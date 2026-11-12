- **P3 — [test_web_route_table.py:331](tests/unit/test_web_route_table.py#L331): delegation check accepts inline processing.** A handler containing `return list(_news_item(*row) for row in _news_rows(...))` passes despite moving the mapping back into the handler. The assertion checks only `Call`/`Await`. Fix: validate the delegated helper and reject inline comprehensions/generators.

- **P3 — [onboarding.md:343](src/app/usecases/sources/onboarding.md#L343): delegation guarantee overstates the implementation.** For `GET /api/source-onboarding/check-status`, the handler calls `dict(deps.source_intake.status())`, not a module-level function taking `deps`. Fix: document this exception or extract the helper.

No findings:
- Bad-body 422 details remain unchanged, including blank import text, malformed JSON, and `{"batch_id": true}`.
- Body reading and model validation precede table creation; candidate validation remains in the thread pool.
- Parameter assertions and mutation-survivor tests check their stated cases; `pages.md` references the renamed test correctly.

The exact requested pytest run passed: **131 tests**. No files changed.