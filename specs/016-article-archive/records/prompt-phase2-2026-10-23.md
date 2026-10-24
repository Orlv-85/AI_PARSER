# Prompt: spec 016 phase 2 - seed and operator commands (2026-10-23)

You implement **phase 2 of spec 016** (tasks T005-T007) in `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`.
Phase 1 is merged (PR #92) and deployed (v0.1.121, migration `e7b4c2a9d150` on prod). The
coordinator is session `ai-parser-d4`; report to it by SendMessage when done. Do not ask the owner
design questions (AGENTS.md "Owner And Questions": decide, then report).

## Read first

1. `AGENTS.md`.
2. `specs/016-article-archive/tasks.md` (Phase 2), `plan.md` sections "Retention, purge, access",
   "Capture steps" (steps 1, 2 and 8 only), "Constants", tests table.
3. `src/app/core/archive/capture.md`, `capture.py`, `src/app/storage/archive.py` (phase 1),
   `src/app/cli/main.py` (how commands and sub-apps are registered; `prune` as an example),
   `docs/deploy.md` (operator section).

## Steps

1. Worktree: `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER fetch` then
   `git -C /Users/vyacheslavorlovskiy/GitHub/AI_PARSER worktree add ../AI_PARSER-wt-016-p2 -b feat/016-archive-cli-20261023 origin/master`.
   Work only there; checks with `PYTHONPATH=src ../AI_PARSER/venv1/bin/<tool>` from the worktree root.
2. Code doc first: extend `capture.md` Behavior with the rules this PR ships (capture window and
   `--all`, `--no-download`, summary fields, status, purge dry run / `--apply`), each with its
   `Tests:` line; Code map gets the CLI entry.
3. T005: `capture(...)` in `capture.py` with steps 1, 2 and 8 of plan.md (window or `--all`, sync
   via `archive_articles`, summary); download steps are phase 3 - with downloads not yet built,
   `--no-download` behavior is the only path, and the command must make no network request.
   `ai-news archive capture [--all] [--no-download] [--max-seconds N]` and `ai-news archive status`
   (totals by state, versions, size, coverage per plan.md as far as it needs no downloads).
   Large `--all` over ~7000 articles: batch the rows (do not load all content at once) and commit
   per batch.
4. T006: `ai-news archive purge (--url U | --source KEY | --host H) [--apply]` on `ArchiveRepo.purge`;
   dry run by default, prints documents and versions; exactly one selector, else exit code 2 with a
   message.
5. T007 tests (names exactly as in tasks.md), in `tests/unit/test_article_archive.py`; CLI tests via
   `typer.testing.CliRunner` on a temp SQLite DB. `docs/deploy.md`: operator commands for seed,
   status, purge (commands only, no Behavior repeated).
6. Checks: scoped tests; `ai-news archive --help`, `archive capture --all --no-download` and
   `archive status` against a copy of the local SQLite DB (never the main folder's DB file); full
   gate: `make lint PYTHON=../AI_PARSER/venv1/bin/python`, `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest`,
   `PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py`.
7. Commit `feat(archive): archive capture/status/purge commands (016 phase 2)` with your harness's
   Co-Authored-By line; push; `gh pr create --base master --title "feat(archive): archive capture, status, purge commands (016 phase 2)" --body "<summary, checks with results, local seed output, decisions, open questions>"`.
   Do not merge, do not tag, no prod access (the prod seed is the owner's yes after deploy).

## Out of scope

Downloads, retries, raw page cache (phase 3); nightly job and timers (phase 4); admin stats;
restoring the 79 articles pruned on 2026-10-23 from the dump; `scripts/db_maintenance.sh`.

## Report to the coordinator (SendMessage to `ai-parser-d4`)

PR link and head SHA; files changed; tests added; full gate summary; output of the local
`archive capture --all --no-download` and `archive status`; decisions not fixed by the spec, one
line each; doubts about the spec.
