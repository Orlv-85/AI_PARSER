# Prompt: review of PR #188 (018 world stream W5, Jev steps A and B) (2026-11-01)

You review PR #188 (`feat/018-world-w5-jev`). You did not write it. **Read-only: no commits,
pushes, merges, PR comments, paid calls, network to GDELT or production access.** Never run any
command that changes `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself (no `gh pr checkout`, no
`git checkout` there); you may read files there. Report in English.

## Read

- `gh pr view 188`, `gh pr diff 188`, `gh pr checks 188`.
- Implementer worktree (do not edit it): `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-acf9aac8a7e26b4f6`.
  For your own runs and mutations, create a worktree of `origin/feat/018-world-w5-jev` under your
  scratchpad named with `pr188`; never remove one you did not create; remove yours at the end.
- `AGENTS.md`; plan `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md`
  sections 4, 6.1 (Jev, Cost cap, Failure handling) and 6.2 step 5; the W5 prompt
  `records/prompt-item5-w5-2026-11-01.md` (on the PR branch).
- Implementer report (judge each decision in it):
  `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/7ecb9336-da3a-4d18-988a-5e90205c07d1/scratchpad/coord-records/specs/018-daily-inference/records/report-item5-w5-2026-11-01.md`.

## Check

1. **Money (most important).** The owner approved a world Jev budget of $0.10 per day as a hard
   stop. The journal file name contains the cap (`journal-world-stream-1-<cap>.sqlite3`) and the
   budget day is the GDELT day D, not the real day. Can real spend in one calendar day exceed $0.10:
   two runs with different `--max-usd`; runs for D and D+1 on the same real day (catch-up); reruns
   after a crash; step A and B together? Compare with how `bulletin assess` documents its "known
   limit". Propose the smallest fix that makes $0.10 per real day hold, or argue why it holds.
2. Step A sends only title, domain and language (no URL, no text); question version separate;
   `RUBRIC_VERSION` and `WORLD_CHANGE_VERSION` unchanged; the `world_change.py` refactor keeps
   `bulletin assess` behavior (run its tests).
3. Cluster logic: representative choice, followers, late outlet of a screened cluster, ranking by
   confidence x distinct domains, top N never exceeded across reruns and windows.
4. State machine and failures: requeue by `last_error` prefix and `MAX_ATTEMPTS`; Jev failure vs
   journal stop; candidates never stuck (for example a follower whose representative failed 3
   times); window D and D-1 vs the plan's "pending up to 2 days".
5. Text seam for W6 and step B only with `text_ready`; `--dry-run` writes nothing (no tables, no
   journal, no state); missing `JEV_API_KEY` exits 2.
6. Not wired into the 04:00 job; no timer; FR-016 import rules still hold.
7. Doc `world.md` and `world_change.md` match the code; every rule names tests or says none;
   `scripts/check_code_docs.py --diff origin/master --strict` (exit code).
8. Tests check behavior, not mocks. **Mutation checks**: at least 8 hand mutations in
   `world_screen.py` and `screen.py` (cap check, threshold comparison, top N, follower copy, requeue
   attempts, prefix filter, dry-run guard, title-only state); list each with killed / survived.
9. Run in your worktree:
   `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_world_screen.py tests/unit/test_world_storage.py tests/unit/test_world_change.py tests/unit/test_deepseek_digest.py | tail -3`
   (find the real world_change test file name), ruff on `src tests`.
10. Advisory: `~/tools/unclebob/dryer/dryer` and `~/tools/unclebob/crapper/crapper --no-coverage` on
    the new source files; report duplicates >= 0.8 and complexity >= 10; delete `.metrics/`.

## Report (final message)

Verdict (merge / merge after fixes / do not merge); findings by severity with file:line, the concrete
failure and a one-line fix; "must fix" separate from "nice to have"; the mutation table; checks you
ran with results.
