# Prompt: review one T2 refactoring PR (2026-11-01)

You review **one** PR of the T2 refactoring plan; the PR number on GitHub and the plan row number are
given in the message that points you here. You did not write it. **Read-only: no commits, pushes,
merges, PR comments, ssh or paid calls.** Report in English.

## Read

- `gh pr view <PR>`, `gh pr diff <PR>`, `gh pr checks <PR>`.
- The plan: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/plan-t2-refactor-2026-11-01.md`
  (the row, the rules above the table, section 3 what not to touch).
- The task given to the implementer: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/prompt-t2-implement-2026-11-01.md`.
- `AGENTS.md`; the code doc that covers the changed files.
- Check the PR branch out in your own `git worktree add --detach` under your scratchpad; remove it
  at the end. Python: `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`.

**Never run git, gh or any mutation inside `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself**
(no `gh pr checkout`, no `git checkout`, no edits there): create your worktree with
`git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add --detach <scratch path> origin/<branch>`
and run every later command with absolute paths inside it. Check exit codes directly, not through
`| tail`.
Other agents share the scratchpad: name your worktree with the PR number (e.g.
`scratchpad/review-pr<PR>`), never a generic name, and never remove a worktree you did not create.
Local mypy in a worktree is unreliable for new modules (stale editable install in `venv1`, see
`docs/troubleshooting.md`); CI is the authority for mypy. A typed local or `cast` that fixes
`no-any-return` is the documented idiom, not a workaround.

## Check

1. Behavior is preserved: no change to CLI, API, schema, stored data, thresholds, reader-visible
   wording, paid calls, deploy scripts. Name any behavior difference, however small (error text,
   ordering, exception type, None vs missing).
2. Deletions: repeat the caller check yourself for each deleted name (grep over `src`, `tests`,
   `scripts`, `deploy`, templates, `pyproject.toml`, string-based access such as `getattr`, Typer or
   FastAPI registration).
3. Tests: they pin real behavior, not mocks of the code under change; new tests pass on the old code
   (for test-only PRs: run them against `origin/master` source). Try at least two mutations of the
   changed code and say whether the tests catch them.
4. The covering code doc stays true; `scripts/check_code_docs.py`.
5. Scope: only the files of the plan row (plus tests and doc).
6. Run: scoped tests of the changed area and ruff on `src tests`. Advisory: crapper `--no-coverage`
   and dryer on the changed source files (delete `.metrics/`, `target/`).

## Report (final message)

Verdict (merge / merge after fixes / do not merge); findings with file:line, failure, one-line fix;
must fix vs nice to have; checks and mutations run with results.
