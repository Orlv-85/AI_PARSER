# Prompt: future publication dates become the collection time (2026-10-27)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. Investigate, fix with tests,
open a PR. Do not merge, do not tag. Production is read-only for you (SELECT and log grep only).

## Owner decision (2026-10-27)

An article whose publication date is in the future gets the collection time instead (owner: yes).
Case: on 2026-10-23 two articles of `raw-githubusercontent-com-alan-turing-institute-ai-rss-feed-5`
had `published_at` 2026-10-31 (8 days ahead).

## Rules

- Read `AGENTS.md` ("Feature Docs Next To Code", "Validation") and `src/app/core/ingestion/pipeline.md`.
  Behavior change starts in the doc: add the rule (name a constant, e.g. a tolerance so a few hours
  of timezone skew are not "future"; decided 2026-10-27 (agent): 24 hours unless the code already
  has a similar bound - then reuse it), the tests, and one Decisions line.
- Find where `published_at` is parsed/set for RSS and HTML items, and how `publication_date_kind`
  ("published" / "updated" / "unknown") is used. Choose the place so both RSS and HTML get the rule
  and so admission, digest day assignment and archive see the corrected date. Mark the replaced date
  in a way that already exists (e.g. kind "unknown") only if that keeps every existing rule; say
  which in the report.
- Existing rows on prod: do not change them. In the report, give a SELECT that lists stored
  articles with `published_at` > their collection time + tolerance (run it read-only and paste the
  count), and say what a one-off fix would be (do not run it).
- Tests first (fail before, pass after) next to the existing ingestion tests.

## Steps

1. `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b fix/future-dates-20261027 ../AI_PARSER-wt-future origin/master`. No git writes in the main folder.
2. Doc, tests, fix. Checks from the worktree: `make lint PYTHON=../AI_PARSER/venv1/bin/python`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider` (full, read the summary
   line; never wait with `until grep`), `../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
3. Commit `fix(ingestion): a future publication date becomes the collection time` ending with
   `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push; `gh pr create --base master`, body
   ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final answer)

PR URL and SHA; where the rule lives (file:function); the constant and its value; doc rule; tests
(fail before / pass after); full gate result; prod count of stored future-dated articles and the
proposed one-off fix.
