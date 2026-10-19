# Prompt: Verification review of the PR #39 fix pass (2026-10-19)

You are an independent READ-ONLY reviewer. PR #39 (`feat/006-daily-ai-signals`) in
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` was reviewed at `8f30549`; four reviews were consolidated
into findings F1-F22 and N1-N3, which the implementer then fixed. Your job is to verify **the fix
diff only**: is each finding really fixed, completely, without new defects? Do not re-review the
whole feature.

## Setup (separate worktree; do not work in the main folder)

```bash
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
SHA=$(gh pr view 39 --json headRefOid -q .headRefOid)
git worktree add --detach ../AI_PARSER-verify-<model> "$SHA"
cd ../AI_PARSER-verify-<model>
git diff --stat 8f30549.."$SHA"
```

`<model>` = short lowercase name of the model you run as. Record `$SHA`. Use
`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1` with `PYTHONPATH=src`, no `.env` in the worktree
(see `docs/troubleshooting.md`). No provider calls, no production access, no network writes.

## Read first

- `docs/daily-ai-signals-pr39-review-consolidated-2026-10-19.md` (F1-F17, N1-N3)
- `docs/prompt-daily-ai-signals-review-fixes-2026-10-19.md` (incl. Addendum F18-F22)
- `docs/prompt-daily-ai-signals-f19-decision-2026-10-19.md` (final F19 rule)
- PR description (`gh pr view 39`): finding -> commit -> test table
- `.specify/specs/006-daily-ai-signals/dry-run.md` sections 8-9 (Phase 7 numbers)
- The original four reports `docs/daily-ai-signals-pr39-review-*-2026-10-18.md` for reproductions

## What to check

For every finding F1-F22 and N1-N3:

1. The code change addresses the root cause described (not only the reproduced example).
2. The named regression test exists, asserts the right behaviour, and would fail on `8f30549`
   (run it there if cheap: `git stash`-free approach - check out the test file into a temporary
   copy of `8f30549`, do not modify the PR worktree).
3. No new defect introduced by the fix, especially in:
   - F2/F3/F4/F13/F20/F21 identity and override changes (order independence, homonyms, selector
     stability, plural and vendor-join rules must not merge unrelated names);
   - F9 `url_canonical_hash` added inside migration `b6d1f0a7c3e5` (upgrade/downgrade, create_all
     interaction, PostgreSQL and SQLite);
   - F18 extraction input fallback (grounding against the same text, content hash changes, prompt
     injection via summaries);
   - F19/F22 New suppression rules (false suppression risk; payload records);
   - F5/F16 web isolation and client JS; F6/F15 rollback and recovery docs; F17 job script.
4. Gate: `make lint PYTHON=...`, full pytest once (with PostgreSQL if you can start a disposable
   container; otherwise say it was skipped), `bash -n scripts/*.sh`.

## Output

Write `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/daily-ai-signals-pr39-fix-verification-<model>-2026-10-19.md`
(do not commit; touch nothing else in the main folder):

- Header: SHA, commands run and results.
- Table: finding ID -> fixed (yes / partially / no) -> evidence (file:line, test name, result) -> note.
- New findings introduced by the fixes (ID V01..., severity blocker/major/minor/nit, file:line,
  failure scenario, evidence, suggested fix, confidence).
- Verdict: merge-ready / merge after fixes.

Stop after writing the report. Do not fix code, push, comment on the PR or remove the worktree.
