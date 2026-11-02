- **P3 — [world_change.md:44](src/app/core/bulletin/world_change.md#L44):** The fitting guarantee omits the intended empty-content exception. With model `"m"`, title `"ж"*1024`, summary `"ж"*4000`, and empty content, the unchanged request totals **35,344 bytes including allowance** and is rejected. Fix: document this exception and add coverage. Summary truncation is outside the executor’s specified scope.

In-memory mutation results:

| Mutation | Test that kills it |
|---|---|
| Search uses `middle - 2` | `test_long_non_ascii_state_is_cut_to_fit` |
| Remove 2,048-byte allowance | `test_request_fits_matches_reservation` |
| Always truncate fitting content | `test_fitting_state_is_unchanged` |
| Omit article ID | `test_failure_log_names_the_article` — both variants |
| Revert truncation | Both oversized-content variants |

**Survivor:** lowering the default content limit to 15,999. Add an unchanged-body assertion for fitting 16,000-character ASCII content. The existing fitting-state test also passes against the original implementation, appropriately serving as compatibility coverage.

The search terminates, preserves complete astral code points, and finds the longest fitting prefix. No additional reservation mismatch, request-key change for fitting inputs, import cycle, or logging-field regression found. Daily enrichment and `world_screen` control flow remain unchanged.

Validation: **75 passed, 1 warning**; mypy passed across **264 source files**. No files edited.

**clean** — no merge-blocking findings.