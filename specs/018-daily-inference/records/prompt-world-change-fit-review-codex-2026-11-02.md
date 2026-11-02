# Prompt (Codex review, gpt-6-astra high): world_change request fits the Jev byte bound (2026-11-02)

Read-only review. Directory (a git worktree of branch `fix/018-world-change-fit`; changes are
uncommitted or in the last commit, compare with `origin/master`):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/world-change-fit`.
Do not edit files, commit, push or use gh. No network, no paid calls.

## The task that was implemented

The executor's prompt is `docs/work/prompt-018-world-change-fit-codex-2026-11-02.md` in the main
folder `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` (read it). In short: a world_change Jev request
that would exceed the byte bound of `reservation` (`ensure_ascii` JSON, 6 bytes per non-ASCII
character) is sent with its content cut to the longest prefix that fits; a request that fits stays
byte-for-byte the same (same journal request key); failure logs carry the article id.

## Check

1. `git -C <worktree> diff origin/master` (and `git status` for untracked files). Read every changed
   file in full around the change.
2. Correctness, with concrete inputs:
   - Is the cut body always within the bound that `reservation` enforces (same formula, same
     encoding, the overhead included)? Any input where `body()` returns a body that `reservation`
     still rejects, other than the documented "even empty content does not fit" case?
   - Is a fitting request unchanged for every article shape (content present, content empty with a
     summary fallback, missing attributes)? Could the default path change any existing request key?
   - Binary search: correct bounds, terminates, deterministic, truly the longest prefix?
   - Surrogate pairs / astral characters (emoji, CJK extension): can a cut split them or change size
     accounting?
   - Is the summary-fallback state (no content) cut at all when too large? Is that a gap?
   - `ask` context: any path where the failure or stop line loses fields or raises?
   - Import cycles, mypy, behavior of `world_screen._assess` and daily enrichment unchanged.
3. Doc `src/app/core/bulletin/world_change.md`: rules match the code; each rule names tests that
   exist and actually check it.
4. Tests: would each new test fail if the code were reverted? Do a few hand mutations (e.g. off by
   one in the search, drop the overhead from `jev_request_fits`, always cut, never add the article
   id) and say which tests kill each; name surviving mutants.
5. Run: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_world_change.py tests/unit/test_world_screen.py | tail -1`

## Report (your final message)

Findings ranked most severe first: file:line, the problem, a concrete failing input, a fix in one
line. Then the mutation results. Then "clean" if nothing must change before merge. Be brief.
