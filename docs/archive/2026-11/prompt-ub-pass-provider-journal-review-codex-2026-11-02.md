# Prompt (Codex review, gpt-6-astra high): ub-mode pass 1, provider journal (2026-11-02)

Read-only review. Directory (git worktree of branch `refactor/ub-provider-journal`, changes
uncommitted; compare with `origin/master`, include untracked files):
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/worktrees/ub-provider-journal`.
Do not edit files, commit, push or use gh. No network, no paid calls. Do not spawn a sub-agent.

The executor's prompt: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-ub-pass-provider-journal-codex-2026-11-02.md`.
This is a pure refactor of the payment journal every paid Jev/DeepSeek call goes through, plus
characterization tests and a new feature doc. Any behavior change is a defect.

## Check

1. `git diff origin/master` plus every untracked file, read in full.
2. Equivalence of `src/app/storage/provider_journal.py`, method by method, old vs new: same SQL,
   same order of reserve / dispatch / response commit / validation, same exceptions and messages,
   same `fail()` error types, same return values, same transaction boundaries (`with self.db`,
   `commit`, `rollback`), same reads of local state after an extracted helper (a value the old code
   reassigned and used later). Name any difference with a concrete input.
3. Feature doc `src/app/storage/provider_journal.md`: does each rule state what the code does (not
   more, not less)? Does each named test exist and check that rule? Missing important guarantees
   (cap per provider and total, replay of an identical body, failed-call block and review, transient
   release)? Any "decided (agent)" line that a source actually states differently? Header, covers,
   docstring link, registrations in the three README files.
4. Tests `tests/unit/test_provider_journal.py`: real assertions on journal state (rows, states,
   committed amounts, order of calls), not only on "no exception"? Would they catch a reorder of
   reserve and dispatch, a dropped cap check, a changed error type? Hand mutations on the new code
   (swap `_record_response` and `_validate_response`, drop the total-cap check, change `>` to `>=` in
   the saved-amount check, skip `before_dispatch`) and which tests kill them.
5. `docs/troubleshooting.md` new case: accurate and useful, or noise from the executor's own
   environment?
6. Run: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.venv/bin/pytest -q -o addopts="" tests/unit/test_provider_journal.py tests/unit/test_provider_requests.py tests/unit/test_world_change.py tests/unit/test_bulletin_writer.py tests/unit/test_daily_enrichment.py | tail -1`

## Report (your final message)

Findings ranked most severe first: file:line, problem, concrete failing input, one-line fix. Then
mutation results. Then "clean" if nothing must change before merge. Be brief.
