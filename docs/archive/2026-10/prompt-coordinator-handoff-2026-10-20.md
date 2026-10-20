# Coordinator handoff (2026-10-20)

## Prompt for the new session

You continue as the **coordinator** for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. The owner
writes in Russian; answer in Russian. Read `AGENTS.md`, your memory files and this file, then
report the state in a few lines and ask the owner what to do. First suggestion: item 1 below.

## How we work

- Owner decides. Coordinator plans, writes prompts for other sessions
  (feature: `specs/<NNN>/records/prompt-<task>-<date>.md`, other: `docs/`), reviews every checkpoint, verifies production.
- Larger features: planner session, then a different implementer session; each in its own git
  worktree. Small tooling/docs: coordinator may do it in its own worktree.
- Main folder stays on `master`; the owner is refactoring there now - no git writes in it.
- Merge only on an explicit "мержи N". Release = push tag `vX.Y.Z` (deploy-release.yml), only with
  the owner's yes. Prod (`ssh ai-news`) is read-only; every write needs the owner's yes.
- Docs-only PRs: commit + PR without the full gate (say so in the PR).
- Allowed without prompts (owner's settings): `gh pr merge`, `gh run list/view/watch`,
  `git worktree remove`, `git branch -d/-D`, `git push origin --delete`. Run them as separate
  commands, not chained with `&&`.
- Every feature gets a code doc next to its main module (AGENTS.md "Feature Docs Next To Code");
  include it as a task in every implementer prompt and check it in reviews.

## State

- Production: `v0.1.105` (tag on `2fc8751`, docs layout PR #47; released 2026-10-20 06:40 UTC). Master `c22b6e9` adds only AGENTS.md compaction (no release needed). Migrations up to
  `c3a8e5d27f14`. Server `.env`: `AINEWS_DAILY_SIGNALS_ENABLED=true`, no `APP_IMAGE` line (backup
  `.env.bak-20261019-appimage`). Manual compose runs: `export APP_IMAGE="$(cat .last_deploy_image)"`.
- 006 Daily AI Signals + 007 Daily Signals Brief live. Snapshots `daily-signals-3` for
  2026-10-10..18. Briefs (`daily_signal_briefs`, model `deepseek-v4-pro`, prompt
  `daily-signals-brief-3`): 10-10..18 `ok` except 10-14 `invalid` (kept; re-gen needs deleting the
  row - owner decision). Backfill cost $0.041 ledger.
- Code docs: `src/app/core/daily_signals.md` (code map), `src/app/README.md` (overview),
  `docs/README.md` (index). Sync check `scripts/check_code_docs.py`: pytest
  `tests/unit/test_code_docs.py` + CI lint step `--diff origin/master --strict`; opt-out commit line
  `Docs-Skip: <reason>`.
- Backlog: `docs/backlog/backlog-todo.json` (B1 off-site backups first, B2 weekly/monthly analytics after
  2026-10-23, B3 archive, B4 Jev, B5-B9 outputs). Also `docs/backlog/article-archive-todo.json`,
  `docs/backlog/jev-novelty-second-opinion-todo.json`.
- Open PRs: none (#48 AGENTS.md compaction merged). Worktrees: only the main folder.

## Open items

1. **Digest 2026-10-19 not published** (nightly 2026-10-20: `provider_outage_unknown_billing`, so
   no signals/brief for 10-19). Handled by a separate session - do not touch. After it is
   republished, check that `daily_signal_reports` / `daily_signal_briefs` have 10-19.
2. **2026-10-23**: Rising/Cooling unlock; check `/` for a normal and a quiet day.
3. Compare the real DeepSeek bill for `deepseek-v4-pro` with the ledger (flash was ~4.5x below).
4. Owner's refactor: when done, check `src/app/core/daily_signals.md` still matches the code.

## Key files

- Specs: `specs/006-daily-ai-signals/`, `specs/007-daily-signals-brief/` (records: `records/`)
- Operator guide: `docs/daily-signals.md`; deploy: `docs/deploy.md`; known failures:
  `docs/troubleshooting.md`
- Jobs: `scripts/run_daily_digest_job.sh`, `scripts/run_daily_fetch_job.sh`
