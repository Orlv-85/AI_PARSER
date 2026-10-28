# Prompt: 017 release R1, delete weekly v2 code (Phase B, tasks T001-T006) (2026-10-28)

You are the **implementer** (background agent, Sonnet) for coordinator `ai-parser-ba`. You did not
write the plan; follow it. One PR, do not merge, do not tag. Production is read-only for you.

## Read first

`AGENTS.md`; `specs/017-weekly-monthly-signals/spec.md`, `plan.md` (weekly v2 decision, deletion
list, Decided, Owner questions), `tasks.md` Phase 1 (T001-T006); `src/app/core/ingestion/pipeline.md`
("Weekly hooks"); `docs/troubleshooting.md`.

## Owner answers (2026-10-28) - add them to `plan.md` in this PR

Add a section "Owner answers (2026-10-28)" right after "Owner questions" in `plan.md`:

- Q1 yes: retire the legacy preview and pages (later releases), delete weekly v2.
- Q2 yes, both briefs, built in one release; the weekly brief is turned on as soon as the page is
  live (no week of waiting); the monthly brief runs from 2026-12-01.
- Q3 yes: completed weeks and months only.
- Q4 yes: month view as the last release.

Also change the Q2 recommendation line ("after the numbers page has been live for a week") nowhere
else; the answers section is the record. In `tasks.md`, mark T-F1 as not needed (Q1 yes).

## Scope of this PR: tasks T001-T006 exactly

- Follow `tasks.md` Phase 1 to the letter. Keep: the legacy Monday report publication
  (`weekly_hooks.py` legacy branch), the legacy read API, the legacy report tables, the `/` preview and
  the `/weekly-ai-analytics*` pages (they go in a later release), the model classes and all
  `weekly_*` tables (dropped by a migration in a later release - no migration now).
- `weekly_publisher_overrides`: confirm with `git grep` it has no non-v2 user before removing it.
- Production-sensitive files (both deploy workflows, `scripts/deploy_prod.sh`,
  `docker-compose.prod.yml`, `deploy/.env.prod.example`): change only what T004/T005 say; keep the
  `.env` strip patterns for `AINEWS_WEEKLY_V2_ENABLED` so an old value on the server is removed, not
  re-added. Show every hunk of these files in the PR body.
- Move-only rule does not apply (this is deletion), but list every deleted top-level name and prove
  with `git grep` on the PR branch that nothing still imports it.
- Docs follow AGENTS.md "Feature Docs Next To Code": `pipeline.md` first; delete
  `docs/weekly-analytics.md` and its registrations.

## Checks (from the worktree)

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b feat/017-r1-weekly-v2-cleanup ../AI_PARSER-wt-017r1 origin/master
cd ../AI_PARSER-wt-017r1
make lint PYTHON=../AI_PARSER/venv1/bin/python
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1
../AI_PARSER/venv1/bin/python scripts/check_code_docs.py
bash -n scripts/*.sh
```

No git writes in the main folder. Never `rm -rf` a tracked directory outside what the task deletes
(use `git rm -r` for the deletions).

## Commit and PR

Commit `feat(017): R1, delete weekly v2 code and its collection hooks` ending with
`Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; push; `gh pr create --base master` with:
prod facts (T001), deleted files and names with the grep proof, hunks of production-sensitive files,
checks, what is kept. Body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
Wait for CI (`gh pr checks <N> --watch --interval 30`); fix real failures (read
`gh run view <id> --log-failed`); do not call a CI failure "local only" without proof.

## Report (final answer)

PR URL and SHA; CI result; lines removed (src / tests); deleted names list and grep proof summary;
the production-sensitive hunks in short; full gate last line; anything left for later or unclear.
