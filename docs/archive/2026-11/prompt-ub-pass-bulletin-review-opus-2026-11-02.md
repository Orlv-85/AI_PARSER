# Prompt (Claude Opus reviewer): ub-mode pass 2, bulletin modules (2026-11-02)

Read-only review. Directory (git worktree of branch `refactor/ub-bulletin`, changes uncommitted;
compare with `origin/master` via `git diff 9b680ab`, the base of the branch; include untracked files):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-bulletin`.
Do not edit, create or delete any file in the repo or worktree, do not commit, push, stash or use
gh. No network, no paid calls. Do not spawn sub-agents. For hand mutations copy `src` to
`/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/16013267-5611-4c32-b32a-786cfb3ce4cf/scratchpad/review-bulletin/`
and run tests with `PYTHONPATH` pointing there first and `PYTHONDONTWRITEBYTECODE=1` (stale `.pyc`
hid a mutant for the executor).

The executor's prompt: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-ub-pass-bulletin-opus-2026-11-02.md`.
A pure refactor plus characterization tests and doc test-name updates. Any behavior change is a
defect.

## Check

1. `git diff 9b680ab` in full.
2. Equivalence, function by function, old vs new:
   - `phrases.validate_phrases`: same checks in the same order, same `PhraseError` messages, same
     data accessed (a KeyError where the old code raised one, and none where it did not).
   - `bulletin_input._digest_candidates` and `_world_candidates`: same queries in the same order,
     same filters (answer version), same event key precedence, same outlet fallback; is the new
     shared `_outlet` exactly the old fallback in both places?
   - `world_change.run_assessment`: same summary keys and values in the same key order, same
     commits after each save, same stop handling, `cost_usd` with and without a journal.
   - `writer_grounding.sentence_error`: same order of checks (the first failing check names the
     reason), evidence computed only after the form checks, same defaults.
3. Docs `builder.md`, `world_change.md`, `writer.md`: edits accurate; new sentences ("checks run in
   a fixed order, extra keys allowed", "cost_usd is 0.0 without a journal") true of the code;
   every named test exists and checks its rule.
4. Tests: real assertions? Hand mutations (reorder two phrase checks, swap two grounding checks,
   drop the version filter of answers, `cost_usd` from the wrong provider, skip `session.commit()`
   in the assessment loop, change the outlet fallback order) and which tests kill them.
5. Run: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_bulletin_builder.py tests/unit/test_bulletin_writer.py tests/unit/test_world_change.py tests/unit/test_bulletin_daily.py | tail -1`

## Report (your final message)

Findings ranked most severe first: file:line, problem, concrete failing input, one-line fix. Then
mutation results. Then "clean" if nothing must change before merge. Be brief.
