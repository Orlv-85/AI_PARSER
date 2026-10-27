# Prompt: archive capture counts network timeouts as attempts (2026-10-27)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. Investigate, fix with tests,
open a PR. Do not merge, do not tag. Production is read-only for you (SELECT and log grep only).

## Finding (backlog small_followups)

016 capture: when every host times out (ConnectTimeout/ReadTimeout: our network or DNS is down),
the shared `SourcePageDownloader` does not see it as an outage, so each document's attempt counter
grows; after a few such nights documents reach the give-up limit and are never archived.

## Questions (answer in the report)

1. How the archive capture decides "outage" vs "per-document failure" today (file:function), the
   retry schedule and the give-up limit (constants).
2. Prod read-only: how many archive documents are `failed`/gave up, by error type, and did any
   night have only timeouts? (`ai-news archive status` needs APP_IMAGE, see `docs/deploy.md`
   "Article archive"; or SELECT on the archive tables; logs `/opt/ai-news/logs/daily-archive.log`.)
   Also: the archive `pending` count has stayed at 4014 since 2026-10-24 - explain why (expected
   by design, e.g. outside the capture window, or a bug).

## Fix rules

- Read `AGENTS.md` and the code doc `src/app/core/archive/capture.md` first; behavior change starts
  in the doc (rule, constant, tests, one Decisions line).
- Smallest fix: when a capture run sees only network-level failures (timeouts, connection errors)
  for N consecutive documents across different hosts, treat it as an outage: stop the run and do
  not count the attempts (or roll them back), as the source fetch pipeline does for its own
  outages. Reuse the existing outage mechanism if the downloader has one.
- Tests first, next to the existing archive tests (fail before, pass after).

## Steps

1. `cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b fix/archive-timeouts-20261027 ../AI_PARSER-wt-archto origin/master`. No git writes in the main folder.
2. Doc, tests, fix. Checks: `make lint PYTHON=../AI_PARSER/venv1/bin/python`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider` (full; never wait with
   `until grep`), `../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
3. Commit `fix(archive): a network outage does not count as capture attempts` ending with
   `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push; `gh pr create --base master`,
   body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Report (final answer)

PR URL and SHA; answers 1-2 with numbers; doc rule and constant; tests (fail before / pass after);
full gate result; anything not run.
