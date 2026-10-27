# Prompt: db_maintenance size loop vs the article archive (2026-10-27)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. Investigate, fix with tests,
open a PR. Do not merge, do not tag. Production is read-only for you (SELECT, `ls`, `cat`, log
grep only; never run db_maintenance or any write).

## Finding (backlog small_followups)

`scripts/db_maintenance.sh`: above `DB_MAX_SIZE_GB` it lowers retention step by step and prunes
again. Since spec 016 pruned articles are moved into the archive tables first (archive before
prune), so the database does not shrink, and the loop may keep lowering retention and prune far
more articles than needed.

## Questions (answer in the report)

1. Exact loop logic (file:lines), the size it measures (whole DB? which query?), the step and the
   floor of retention, and what archive-before-prune does to the size.
2. Current prod numbers (read-only): DB size, `DB_MAX_SIZE_GB` and `RETENTION_DAYS` in effect,
   size of the archive tables vs the rest (`pg_total_relation_size`). How close is prod to the
   limit? Has the loop ever lowered retention (logs of db-maintenance runs:
   `/opt/ai-news/logs/` and the GitHub Actions logs `gh run list --workflow db-maintenance.yml`,
   `gh run view <id> --log`)?
3. Is there a real risk of over-pruning today, or only when the DB grows?

## Fix rules

- Read `AGENTS.md`, `docs/deploy.md` (maintenance, "Article archive") and the 016 code doc
  `src/app/core/archive/capture.md`. Do not change `RETENTION_DAYS`, `DB_MAX_SIZE_GB` defaults or
  deploy files' behavior beyond what the fix needs; this is production-sensitive.
- Smallest safe fix, for example: measure the size the loop can actually reduce (exclude the
  archive tables), or stop the loop when a prune step did not reduce the measured size, with a
  clear log line. Choose, and justify in the PR in one or two lines.
- Tests: extend the existing tests of db_maintenance (find them: `git grep -l db_maintenance tests`);
  a test that shows the over-prune before the fix and passes after.
- Docs: `docs/deploy.md` maintenance section if behavior changes; a troubleshooting case only if
  non-obvious.

## Steps

1. `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b fix/db-size-loop-20261027 ../AI_PARSER-wt-dbsize origin/master`. No git writes in the main folder.
2. Investigate, fix, test. Checks: `bash -n scripts/db_maintenance.sh`, `make lint PYTHON=../AI_PARSER/venv1/bin/python`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider` (full; never wait with `until grep`).
3. Commit `fix(maintenance): size loop does not over-prune when rows move to the archive` ending
   with `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push; `gh pr create --base master`,
   body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final answer)

PR URL and SHA; answers 1-3 with numbers; the fix and why; tests (fail before / pass after); full
gate result; anything not run.
