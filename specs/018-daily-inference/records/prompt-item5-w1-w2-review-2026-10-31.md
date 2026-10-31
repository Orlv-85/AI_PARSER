# Prompt: review of PRs #156 and #157, world stream W1 and W2 (2026-10-31)

You review PR #156 (`feat/018-world-w1`, keyword filter) and PR #157 (`feat/018-world-w2`, GDELT
reader; it branches from W1, so review only its own commits on top of W1). You did not write them.
**Read-only: no commits, pushes, merges, PR comments, paid calls or production access.** Report in
English.

## Read

- `gh pr view`, `gh pr diff`, `gh pr checks` for both.
- In the PR worktree `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.claude/worktrees/agent-a2af40ae0626293bf`:
  the plan `specs/018-daily-inference/records/plan-item5-world-sources-2026-10-31.md` (sections 1.2,
  3, 6), the prompt `records/prompt-item5-w1-w2-2026-10-31.md` (owner decisions and the streaming
  invariant), `AGENTS.md`.

## Check

1. Filter: the rules match the plan and the prompt; multilingual matches are sound (false positives
   such as names "Ai", "KI" in German compounds, "IA" in Spanish words; CJK handling); the two bug
   fixes; own-domain logic against `sources.yaml`.
2. Reader: GKG column use, file name builder (primary and translation sets, UTC day boundaries),
   retries and missing-file handling (`partial` rule), malformed rows, and above all the streaming
   invariant: one file at a time, temp file deleted on every path (exceptions, early stop), memory
   bounded. The production server has 3.6 GB free disk and 2 GB RAM.
3. `ai-news world scan` writes nothing and makes only the requests it says.
4. Doc `src/app/core/world/world.md` matches the code; every rule cites tests or says it has none;
   registrations.
5. Tests test real claims, not only mocks; missing cases.
6. Run in that worktree (it is on the W2 branch; check out W1 with `git stash`-free means, e.g.
   `git worktree add` of your own in your scratchpad if you need W1 alone):
   `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/pytest -q -o addopts="" tests/unit/test_world_filter.py tests/unit/test_world_gdelt.py | tail -3`
   and ruff on `src tests`.

## Report (final message)

Per PR: verdict (merge / merge after fixes / do not merge), findings by severity with file:line, the
concrete failure and a one-line fix, "must fix" separate from "nice to have"; checks you ran.
