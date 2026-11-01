# Prompt: backlog T2 refactoring, implement one PR of the plan (2026-11-01)

You implement **one** PR of the T2 plan: the PR number is given in the message that points you
here. Repo: `ai-news-collector` (`/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`). Report in English.
Do not merge, tag or deploy; no ssh; no paid calls.

## Read

1. The plan: `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/docs/work/plan-t2-refactor-2026-11-01.md`:
   section 1 for the measurements of your files, section 2 for your PR row and the rules above the
   table, section 3 (what not to touch).
2. `AGENTS.md` (test-first rule in Code Changes; feature docs next to code; Working Rules).
3. The `ub-mode` skill, `~/.claude/skills/ub-mode/SKILL.md`; its "Repository rules come first"
   section applies.
4. The code doc that covers your files (named in your row), before changing code.

## Rules

- Own isolated worktree from `origin/master` (`git fetch origin` first). Never edit, commit or pull
  in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER` itself. Python:
  `PYTHONPATH=src /Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`; pytest with
  `-o addopts="" ... | tail -1`.
- Behavior-preserving only: no change to CLI flags, API responses, schema, stored data, thresholds,
  wording readers see, paid-call budgets, deploy scripts. If the plan row turns out to need one,
  stop and say so in the report instead of doing it.
- Pin first: before moving code, make sure tests cover the behavior you touch (existing or new);
  for new tests, see them pass on the old code. For deletions, show the caller check (grep over
  `src`, `tests`, `scripts`, `deploy`, templates, `pyproject.toml` entry points, dynamic imports by
  string) and list each deletion with its reason in the PR body.
- Only the files of your row (plus tests and the covering doc). Other T2 PRs run in parallel in
  other worktrees; do not touch their files.
- Advisory after the change: `~/tools/unclebob/crapper/crapper --no-coverage <changed source files>`
  and `~/tools/unclebob/dryer/dryer <changed source files>`; put before/after numbers in the PR body;
  delete `.metrics/` and `target/` afterwards.

## Local mypy caveat

`venv1` has an editable install pointing at the main folder (on an older master). In a worktree,
mypy resolves `app.*` through it, so a module that exists only in your branch becomes `Any`
(`ignore_missing_imports`). CI is the authority for mypy, but under this repo's config names
imported from `app.*` are Any in CI as well, so `no-any-return` is real there too: fix it with the
documented idiom (`cast(T, ...)` or a typed local, never `# type: ignore`; see the troubleshooting
case citing `src.app.core.ingestion.pipeline`).

## Scratch paths

Other agents share the scratchpad. Name any scratch worktree or file with your PR number (e.g.
`scratchpad/t2-pr7-review`), never a generic name like `wt`, and never remove a worktree you did
not create.

## Checks

ruff on `src tests`; scoped tests; `make lint PYTHON=/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/venv1/bin/python`;
full pytest `-o addopts="" | tail -1`; `scripts/check_code_docs.py` and
`scripts/check_code_docs.py --diff origin/master --strict` (the CI mode: a covered file changed
without its doc fails; update the doc where the change is visible, else a commit line
`Docs-Skip: <reason>`).

## PR

Branch `refactor/t2-pr<N>-<short-name>`. Commit messages end with a `Co-Authored-By:` line naming
your model. `gh pr create --base master`, title `refactor(t2): PR<N> <short description>`; body:
plan row, changes, deletions with reasons, tests that pin the behavior, checks with counts,
crapper/dryer before/after, and ends with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final message)

PR link, branch, worktree path; files; checks with counts; crapper/dryer numbers; anything decided
by you (one line each); anything in the plan row that was wrong.

## Ingestion rows 9-13 (added 2026-11-01)

These split functions of the nightly fetch (production-sensitive). In addition to the rules above:
- Log event names and fields, counters, the order of database writes and commits, and exception
  types are observable behavior: keep them identical.
- Pin first: run the branch coverage of the function before the change
  (`coverage run --branch -m pytest -o addopts="" <tests>` then `coverage report -m --include=<file>`),
  add tests for uncovered branches using the existing fixtures (`tests/fixtures/rss`,
  `tests/fixtures/html`), and see them pass on the old code before moving any line.
- Several of these PRs update `src/app/core/ingestion/pipeline.md`: before opening the PR, rebase on
  the latest `origin/master` and resolve doc conflicts.
- If a split does not clearly reduce complexity, ship the tests alone and say so.
