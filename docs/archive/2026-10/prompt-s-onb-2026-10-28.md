# Prompt: S-onb, source onboarding checks and URL normalization (2026-10-28)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. Investigate, fix with tests,
open one PR. Do not merge, do not tag. Production is read-only for you; you need no prod access.

## The two items

1. An HTML source candidate is validated by a single link (one article page). A listing page whose
   first link happens to work passes, even if the rest are not articles.
2. Three URL normalizations: `normalize_candidate_url` (onboarding), `_url_key` in
   `src/app/web/source_intake.py` (builds on it), and `canonicalize_url` (the fetch pipeline). The
   same source can be seen as new by onboarding and as a duplicate by the pipeline, or the reverse.

## Rules

- Read `AGENTS.md` ("Feature Docs Next To Code", "Validation") and the code doc
  `src/app/core/sources/onboarding.md` first (it already names these in its code map). Behavior
  change starts in the doc: rule, constant, tests, one Decisions line each.
- Item 1: validate an HTML candidate by a small number of links (a constant, e.g. 3; decided by
  you, say why), all of which must pass the existing article checks; keep paid model calls per
  candidate within the current budget rules (`SourceReviewer`, `_PROMPT_VERSION`): if the change
  adds paid calls, do not make it, describe it and stop (owner money question).
- Item 2: make onboarding and intake use the same canonical key as the pipeline where they decide
  "already known / duplicate", or document precisely why they must differ. Do not change
  `canonicalize_url` behavior for stored articles (stored data compatibility); if a stored-data
  change would be needed, describe it and stop.
- Tests first (fail before, pass after) next to the existing onboarding/intake tests.

## Steps

1. `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b fix/s-onb-20261028 ../AI_PARSER-wt-sonb origin/master`. No git writes in the main folder.
2. Doc, tests, fix. Checks: `make lint PYTHON=../AI_PARSER/venv1/bin/python`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts=""` (full; read the
   last line), `../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
3. Commit `fix(onboarding): validate HTML candidates by several links, one URL key` (adjust to what
   was done) ending with `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push;
   `gh pr create --base master`, body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final answer)

PR URL and SHA; per item: what was wrong (file:line), the fix or why not, tests (fail before / pass
after), the constant; whether paid calls change; full gate last line; owner questions if any.
