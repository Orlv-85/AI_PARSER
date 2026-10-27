# Prompt: J1 offline experiment, Jev as a second opinion for New (2026-10-27)

Executor: background agent (Sonnet) of coordinator `ai-parser-ba`. Offline only: nothing changes on
prod, on the site, in `src/` or in `tests/`. Owner approved the paid Jev calls on 2026-10-27 with a
hard cap of **$1.00** in total.

## Read first

- `docs/backlog/jev-novelty-second-opinion-todo.json` (problem, idea, facts, draft_question, task J1).
- `specs/006-daily-ai-signals/prompt-gate.md` (labelled New items of 2026-10-12..16: displayed and
  hidden, OK / BAD / uncertain, the recall list) and `src/app/core/daily/signals.md`.
- `src/app/core/jev.py` (request body, question types, `JevInputTooLarge`), and the earlier offline
  pilots for method and style: `docs/archive/2026-10/report-jev-entailment-pilot-2026-10-23.md`.

## Rules

- Prod is read-only: `ssh -o BatchMode=yes ai-news` with `SELECT` only (`docker exec -i ai-news-db
  psql -U ainews -d ainews` with SQL on stdin) or `scp` of a file you exported with `\copy ... TO
  STDOUT`. No writes, no restarts.
- Jev key: `JEV_API_KEY` from `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER/.env`; never print it.
  Endpoint and body as in `src/app/core/jev.py`. Use the model the app uses (`jev_model` setting).
- Budget: estimate input tokens before calling; keep a running cost from the response usage (or
  from 0.042 USD per million input tokens if no usage is returned); stop at $1.00. Cache every
  answer on disk so nothing is paid twice.
- Throwaway code and data live in the scratch dir
  `/private/tmp/claude-501/-Users-vyacheslavorlovskiy-GitHub-AI-PARSER/ef9ee6d8-3194-45a0-9a65-7c1b58b42256/scratchpad/j1/`,
  not in the repo.
- The novelty question is a new, separate question (draft in the backlog file); never touch the
  admission rubric.

## Steps

1. Export the in-scope articles of 2026-10-12..16 (the same scope as `prompt-gate.md`: about 369) with
   the text the signals pipeline sees.
2. Ask Jev the draft novelty question per article. Record choice and probability.
3. Join with the labelled items of `prompt-gate.md`. For thresholds 0.5, 0.6, 0.7, 0.8, 0.9 of
   `new_release_now`, report: precision of displayed New, precision of uncapped New, recall, which
   grey-zone items are removed, which OK items are lost.
4. If budget remains: the per-entity variant on the New candidates only.
5. Write the report `specs/006-daily-ai-signals/records/report-jev-novelty-j1-2026-10-27.md` (in a
   worktree: `git worktree add -b docs/jev-novelty-j1-20261027 ../AI_PARSER-wt-j1 origin/master`):
   method, cost, the threshold table, examples, recommendation (adopt with threshold / drop), risks.
   Commit it (only that file) with `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`, push,
   `gh pr create --base master` (docs-only; body ends with
   `🤖 Generated with [Claude Code](https://claude.com/claude-code)`). Do not merge.

## Report (final answer)

PR URL; total calls and cost; the threshold table; recommendation in two lines; anything not done.
