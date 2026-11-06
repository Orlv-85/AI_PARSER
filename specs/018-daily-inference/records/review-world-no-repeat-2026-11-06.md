# Review (Codex gpt-6-astra high): PR #215, world story not repeated (2026-11-06)

Prompt: `prompt-world-no-repeat-review-codex-2026-11-06.md`. Saved by the coordinator (the reviewer's sandbox was read-only).

**Verdict: approve.** No blocking findings.

- The code implements D-1 only, ready rows only, all four sections, URL-or-title matching, unchanged digest candidates, and whole-payload fallback when extraction fails.
- Payload compatibility checked against storage and its introduction commit (`8ae9b40`): all four section keys were already emitted. Optional stories are null, not omitted. The writer preserves story titles and links.
- No import cycle or layering problem found.
- Tests exercise observable behavior, and the doc matches the implementation. Referenced regression test names exist.

**Minor note:** [test_bulletin_builder.py:771](tests/unit/test_bulletin_builder.py:771) lacks a case covering the coordinator’s title-normalization correction. Add different URLs with stored title `Court rules on AI evidence` and candidate title `Court rules on AI evidence (5 minute read)`. Current code handles this correctly, but removing `digest_title` from the comparison would escape these tests.

Validation: the exact requested pytest command passed — **127 passed, 1 existing deprecation warning**. No other checks were run.


Coordinator: the minor note is fixed by the case `Court rules on AI evidence (5 minute read)` in `test_world_candidate_syndicated_copy_shown_yesterday_is_left_out`; it fails (8 cases) when `digest_title` is removed from the comparison.
