No findings.

Checked with no findings:

- API responses, HTML, status codes and reachable error paths remain equivalent; `deps.create_all()` stays inside each existing `try`.
- `_read_page` preserves all caller-reachable `explicit`/`start` cases and reads index, report and brief in one session.
- Attributes accessed after close are eagerly loaded; no lazy relationship or deferred-column access was introduced.
- Read use cases preserve repository arguments and query order. `SHOWN_STATUSES` retains the old value and comment.
- Retargeted monkeypatches reach active readers; the provider-code scan includes `period_reads`; no assertions were lost.
- Updated documentation matches the code; no stale names found.

The seven requested test files passed (exit 0). Only those tests were run; one Starlette/httpx deprecation warning was emitted.