# Prompt: fixes to PR #190 after review (018 W6) (2026-11-01)

Continue on `feat/018-world-w6-text` in your worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-ae324b70864b53064`. Same rules
as `prompt-item5-w6-2026-11-01.md` (no paid calls, no main-folder changes, doc first, test first).
Review: `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/review-item5-w6-2026-11-01.md`.

Decided by the coordinator:

1. **No overwrite of real archive documents.** The world stream creates an archive document only
   for a hash that has none. If a document exists (a real article archived by the nightly job), the
   world stream only reads it: stored text -> `text_ready`; no text -> follow item 3. Test first: a
   pre-existing real document keeps `article_id`, `source_key`, title and publication fields after
   `run_texts`.
2. **World documents stay out of the nightly job.** Mark documents the world stream creates (for
   example `source_key="world"`; name it as a constant). Exclude marked documents from
   `ArchiveRepo.window_states` (coverage) and from `due()` when `ids` is None (nightly retries); the
   world stream does its own single attempt. If the nightly job later archives a real article with
   the same URL, the real article's metadata wins (say how and test it). Document in `capture.md`
   (nightly coverage and budget exclude world documents) and `world.md`; one test per exclusion.
   Say in the report whether the archive size warning still counts world texts (acceptable; doc it).
3. **No silent fallback block.** For the world stream, an existing document that is `failed` (any
   `next_attempt_at`) or `gave_up` makes the candidate `no_text` with its reason, so the next run
   falls back to the next outlet. Test it, and add tests for the early give-up branch (survivor
   M14), for "the next run tries the next outlet", and a ranking assertion that `no_text` clusters
   rank by remaining outlets (M10).
4. N bound: state "per run" in the doc; W7 runs it once a day. No daily bound in code.
5. Wrap long doc lines to the files' usual width.

Checks as before (ruff, scoped tests, `make lint`, full pytest, `check_code_docs.py --strict` run
alone after the last commit, report the exit code). Show each new test fails on its mutation, then
passes. Push to the same branch, update the PR body. Copy this prompt into
`specs/018-daily-inference/records/`. Report: commit, items, mutation results, checks with counts,
anything decided by you.
