# Prompt: fixes to PR #188 after review (018 W5) (2026-11-01)

Continue on your branch `feat/018-world-w5-jev` in your worktree
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-acf9aac8a7e26b4f6`. Same rules
as `prompt-item5-w5-2026-11-01.md` (no paid calls, no main-folder changes, doc first, test first).

Review: `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/review-item5-w5-2026-11-01.md`.

Decided by the coordinator:

1. **Money, must fix.** The owner's rule is a hard stop of $0.10 world Jev spend per real (UTC)
   calendar day. Key the world journal by the UTC date of the run (not D), with a fixed cap
   `WORLD_JEV_MAX_USD_PER_DAY` and no cap in the file name. `--max-usd` stays as a run-local lower
   limit only: stop before a request when the journal's committed spend reaches it (log
   `world_cost_cap` either way). Tests first: two runs on the same real day for different `--date`
   and different `--max-usd` never exceed $0.10 in total; a rerun on the next real day gets a new
   budget (inject the clock).
2. **Wedged journal.** Document in `world.md` that a transport/5xx failure is a journal stop that
   needs operator review of the journal (as `world_change.md` explains), and that for the world
   stream the operator must not open a new budget by changing `--max-usd`; give the right step
   (review the call, then what exactly). State that "Jev failure marks only the representative"
   applies to bad answers; add a test with a real `PilotJournal` and a fake 500 showing nothing is
   marked failed and `attempts` is unchanged.
3. **Late outlet**: when a cluster already has a screened member, a new member follows that state
   and confidence without a new request (saves money, avoids duplicate stories). Doc, test.
4. Close surviving mutants: dry-run top N, the rank representative (`min` vs `max`), and the CLI
   above-cap test (set a key; assert exit code, no journal file, no request).
5. Leave as is: top N per window (note it in Decisions as known for W5).

Checks as before (ruff, scoped tests, `make lint`, full pytest, `check_code_docs.py --strict` exit
code). Push to the same branch; update the PR body. Copy this prompt next to the W5 prompt in
`specs/018-daily-inference/records/`. Report: commits, what changed per item, checks with counts,
anything decided by you.
