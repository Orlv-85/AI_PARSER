No findings.

- Auth: equivalent allow/401/303 decisions, `full_text_allowed`, and `session_expired` logging. Eager bearer verification preserves outcomes.
- Routers: status codes, details, bodies, endpoint names, and error boundaries preserved. Table-creation storage errors remain 503; validation stays in the thread pool.
- Weekly: filtering unchanged; `ValueError("report is locked")` still returns 409 with that detail.
- Docs: both documents match the refactor.

The prescribed six-file pytest run passed: 131 tests. No additional checks run; worktree remains clean.