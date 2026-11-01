# Prompt: second fixes to PR #188 after re-review (018 W5) (2026-11-01)

Continue in your worktree on `feat/018-world-w5-jev`; same rules as before (no paid calls, no
main-folder changes, doc first, test first). Re-review: section "Re-review of fix commit 9e07be3" of
`/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/review-item5-w5-2026-11-01.md`.

Decided by the coordinator:

1. Doc gate: add the `PilotJournal.committed_usd()` rule to `src/app/core/ingestion/pipeline.md`
   (the doc that covers `provider_journal.py`), with its test. Rerun
   `scripts/check_code_docs.py --diff origin/master --strict` and report its exit code (not
   through a pipe) after the last commit.
2. Wedged-journal procedure in `world.md`: do not delete the journal; rename it to
   `journal-world-stream-1.sqlite3.reviewed-<UTC time>` after review; rerun with `--max-usd` =
   $0.10 minus `total_committed_usd` from the `world_screen_usage` line, for every further run that
   UTC day; the simple alternative is to wait for the next UTC day.
3. Close the money-relevant survivors with tests: `committed_usd()` counts reserved and unknown
   calls (not only actual cost); the run limit at the exact boundary (spend equal to the limit
   stops); the run limit also stops step B (put a candidate in `text_ready` with a fake text source).
   Also pin that a late outlet follows the oldest screened member (several screened members).
   Show each new test fails on the matching mutation, then passes.

Checks: ruff, scoped tests, `make lint`, full pytest. Push to the same branch, update the PR body.
Copy this prompt into `specs/018-daily-inference/records/`. Report: commit, items, mutation results,
checks with counts.
