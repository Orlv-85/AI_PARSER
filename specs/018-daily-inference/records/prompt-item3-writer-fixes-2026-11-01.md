# Prompt: fixes to PR #195 after review (018 item 3) (2026-11-01)

Continue on `feat/018-bulletin-writer` in your worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-a6bc35051d90418ce`. Same rules
as `prompt-item3-writer-2026-11-01.md` (no paid calls, no main-folder changes, doc first, test
first). Review: `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/review-item3-writer-2026-11-01.md`.

Decided by the coordinator:

1. Per-story grounding test: a number and a name present only in story A, used in story B, are
   dropped. Show the "all-stories evidence" mutation now fails.
2. Name match for the writer by whole words (word-boundary token set), so "Meta" no longer passes
   on "metadata"; keep the daily brief byte-identical (a parameter of `grounding_error` with the
   old behavior as default; the brief tests unchanged). Weekday and month names in model text must
   appear in the story's text (no calendar exemption for the writer). Tests for both.
3. `writer.md` "Cannot catch": spelled-out numbers; straight single-quote quotes (the prompt asks
   for double quotes); wrong meaning and attribution with real names and numbers (FR-022 review).
4. Pin `STORY_TEXT_MAX` with a literal in a test; apply the copy check to the story headline and
   the gloss too (test); pin "Never copy" and "every name and number must stand in the supplied
   text" in the prompt test.
5. Docs: `--max-usd` limits the UTC day's total writer spend (wording); a failed call blocks further
   writer calls that UTC day until the journal is reviewed (say what the operator does, as the world
   stream doc does).

Checks as before (ruff, scoped tests, `make lint`, full pytest, `check_code_docs.py --strict` run
alone after the last commit, report the exit code). Show each new test fails on its mutation. Push
to the same branch, update the PR body. Copy this prompt into `specs/018-daily-inference/records/`.
Report: commit, items, mutation results, checks with counts.
