# Prompt: F1 pipeline findings (2026-10-27)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. Investigate, fix with tests,
open one PR. Do not merge, do not tag. Production is read-only for you (log grep; SELECT only if
needed).

## The four findings

They come from the review of PR #54 and were left out of the pipeline refactor
(`docs/archive/2026-10/prompt-pipeline-refactor-2026-10-20.md`, "Out of scope"). Read the review:
`gh pr view 54 --comments` and `gh api repos/Orlv-85/AI_PARSER/pulls/54/comments`.

1. The meaning of `fetched` in run/source summaries (what it counts vs what the name says; e.g.
   openai_news logs `fetched_items: 1325` for a feed of which 24 are looked at before early stop).
2. No `source_fetch_finished` log line for a failed fetch when semantic admission is off.
3. `FetchSummary.source_count` after a pause (counts sources not fetched?).
4. A source `fetch_failure` treated as complete coverage (weekly / digest coverage).

## Rules

- Read `AGENTS.md` ("Feature Docs Next To Code", "Validation") and `src/app/core/ingestion/pipeline.md`
  first. For each finding: confirm with file:line and a failing test, or refute with evidence.
- Fix only confirmed ones. Behavior change starts in `pipeline.md` (rule, tests, one Decisions line
  each). Log field names that operators or `scripts/` / workflows / `nightly-health.yml` read must
  not be renamed (grep for them); if a meaning changes, keep the old field and add a new one, or
  document why not.
- Nothing reader-visible may change (digest content, site). If a fix would change digest coverage or
  what gets published (finding 4 may), do not change it: describe the effect and stop; it becomes an
  owner question.

## Steps

1. `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b fix/f1-pipeline-findings-20261027 ../AI_PARSER-wt-f1 origin/master`. No git writes in the main folder.
2. Doc, tests, fix. Checks: `make lint PYTHON=../AI_PARSER/venv1/bin/python`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts=""` (full; read the
   last line), `../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
3. Commit `fix(ingestion): F1 pipeline findings (counts, log line, source_count, coverage)` (adjust to
   what was fixed) ending with `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push;
   `gh pr create --base master`, body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final answer)

PR URL and SHA; per finding: confirmed/refuted, file:line, fix or why not, tests (fail before /
pass after); log fields touched and who reads them; full gate last line; owner questions if any.
