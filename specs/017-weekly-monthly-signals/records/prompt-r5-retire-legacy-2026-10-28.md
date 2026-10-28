# Prompt: 017 release R5, retire the legacy weekly pages and Monday report (T040) (2026-10-28)

You are the **implementer** (background agent, Sonnet) for the 017 coordinator. You did not write the
plan; follow it. One PR, do not merge, do not tag. Production is read-only for you.

State: `/weekly` is live (R3, v0.1.135) with real weeks. Owner 2026-10-28: retire the legacy weekly
now instead of waiting ("why keep the old one if it does not work"). This is T040 only; the table
drop of weekly v2 (T041) is a separate later release.

## Read first

`AGENTS.md`; `specs/017-weekly-monthly-signals/plan.md` ("What goes, what stays" Stage 3, "Web",
"Decided"); `tasks.md` Phase 5 (T040); `src/app/web/pages.md`; `src/app/core/ingestion/pipeline.md`
("Weekly hooks"); `src/app/core/periodic/signals_period.md`; the legacy code:
`git grep -n "weekly_hooks\|weekly-ai-analytics\|weekly_analytics\|WEEKLY_" src scripts tests docs README.md`
(read every hit before changing it).

## Scope: T040 exactly

- Stop the Monday legacy publish: delete `core/ingestion/pipeline/weekly_hooks.py` (or wherever it
  lives now) and its call site and test; `pipeline.md` first ("Weekly hooks" section goes; Decisions
  and Tests updated).
- `/`: remove the legacy "Weekly AI Analytics" preview section from `digest.html`, `digest.js`,
  `digest.css` (and any server-side preview code feeding it); the R3 line "Week of ...: weekly
  signals" under the daily block stays and is the only weekly element on `/`. Remove the
  "Weekly Reports" nav link; keep "Weekly" (R3).
- `GET /weekly-ai-analytics` and `GET /weekly-ai-analytics/reports` answer 308 to `/weekly` (drop
  query strings; record it); remove them from the auth public list only if a redirect works without
  it (check how the auth middleware treats them; a logged-out reader must get the 308, not a login
  page). Delete `weekly_analytics.html`, `weekly_analytics_reports.html` and their JS/CSS if only
  they use them; package data list updated.
- Keep: `GET /api/news/weekly-analytics`, `/reports`, `/freshness`, the `POST`, their response
  models and the tables `weekly_analytics_reports` / `weekly_analytics_items` (compat, stored data);
  `scripts/digest_generator.py` weekly feed helpers (check with `git grep` whether
  `publish-feed-weekly` or any cron uses them; if they depend on the deleted hook, report, do not
  delete). Keep the weekly v2 model classes and tables (T041 later).
- Any CLI command or setting that only served the Monday publish: remove if `git grep` proves no
  other user; list them. Do not touch deploy workflows, compose or `.env` patterns unless a removed
  setting is passed there (then remove that line and show the hunk).
- Docs: `web/pages.md` (Behavior and tests), `pipeline.md`, `signals_period.md` (Decisions: legacy
  retired 2026-10-28, owner), `docs/README.md`, `README.md`, `docs/troubleshooting.md` mentions,
  `docs/period-signals.md` if it mentions the legacy block. Tests: route table, redirects (308,
  logged out and in), `/` has no legacy preview and no "Weekly Reports" link, the Monday fetch run
  creates no legacy report, the legacy API still answers with stored data.

## Rules

- Readers notice this (owner approved it). Anything else readers would notice: stop and report as
  yes/no with a recommendation.
- Unclear vs. code: decide, write "decided 2026-10-28 (agent): <reason>" in the right doc, list it.
- List every deleted top-level name and file, with `git grep` proof that nothing still uses it.

## Checks (from the worktree)

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b feat/017-r5-retire-legacy-weekly ../AI_PARSER-wt-017r5 origin/master
cd ../AI_PARSER-wt-017r5
PYTHONPATH=src make lint PYTHON=../AI_PARSER/venv1/bin/python
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1
../AI_PARSER/venv1/bin/python scripts/check_code_docs.py --diff origin/master --strict
bash -n scripts/*.sh
```

Use `PYTHONPATH=src` (without it the venv imports the main folder's code). No git writes in the main
folder; use `git rm` for deletions.

## Commit and PR

Commit `feat(017): R5, retire the legacy weekly pages, preview and Monday report` ending with
`Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; add this prompt file at its path under
`specs/017-weekly-monthly-signals/records/`; push; `gh pr create --base master` with: what readers
see now, what stays (API, tables), deleted files and names with grep proof, decided items, checks.
Body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Wait for CI
(`gh pr checks <N> --watch --interval 30`); fix real failures; do not call a CI failure "local only"
without proof.

## Report (final answer)

PR URL and SHA; CI result; lines removed/added (src / tests); deleted names; redirect behavior
logged out; decided items; full gate last line; anything for the owner or unclear.
