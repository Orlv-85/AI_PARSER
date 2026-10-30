# Prompt: coordinator, next session (2026-10-29)

You continue as the **coordinator** of `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. The owner
writes Russian; answer in Russian, short and plain. Owner wants the Claude limit saved: read little,
delegate, keep this session short; start a fresh coordinator session after each big feature.

## Read first (nothing else up front)

1. `AGENTS.md` and your memory (`MEMORY.md` index).
2. From `origin/master` (`git fetch`; the main folder lags): `docs/backlog/coordinator-todo.json`
   (live todo), `docs/work/coordinator-state-2026-10-24.json` (`new_rules_2026_10_24`, `state`).

## State on 2026-10-28 evening

- Prod **v0.1.139**, master `6ce3756` + docs PR #139. No open PRs, no running agents.
- Spec 017 (weekly/monthly signals) fully shipped 2026-10-28 (PRs #130-#138): `/weekly` with brief,
  `/monthly` (first month November, shown 2026-12-01), legacy weekly retired (308 to `/weekly`),
  weekly v2 code and tables gone (DB 182 -> 141 MB). Server `.env` has
  `AINEWS_PERIOD_SIGNALS_ENABLED=true` and `AINEWS_PERIOD_SIGNALS_BRIEF_ENABLED=true`. Code doc:
  `src/app/core/periodic/signals_period.md`; operator guide `docs/period-signals.md`.
- First weekly brief (week 2026-10-19): ok, $0.008; it retells top stories, little on trends.

## First task: check the night of 2026-10-29 (read-only, item PERIOD-1029)

Nightly fetch, digest, archive green (`systemctl status`, logs in `/opt/ai-news/logs/`); the digest
job log has the period-signals step (week 2026-10-19 unchanged, brief `cached`, month skipped, $0).
Mark PERIOD-1029 done in the next docs PR (DeepSeek, see below). Then ask the owner which backlog
item is next (candidates in `coordinator-todo.json`; product/money only as yes/no).

Later checks (in the todo): PERIOD-WEEK-1026 (2026-11-02/03), PERIOD-BRIEF-TRENDS (~11-17),
PERIOD-MONTH-1201, ARCHIVE-LOG-DUP (small fix).

## Rules learned (short)

- Reports to the owner: "Вопрос к тебе" only for real yes/no; own decisions under "Решил сам";
  say plainly if a tag is pending (memory `report-questions-heading`).
- Code: background Sonnet agent, prompt saved first (`specs/<NNN>/records/` or `docs/work/`). Verify
  yourself: CI, full tests `PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1`
  in the worktree (without `PYTHONPATH=src` the venv imports the main folder), key diff hunks only.
- Simple docs: DeepSeek run by you (memory `external-executor-models`), edit script dry-run + `cmp`.
- Tags: owner yes; `git fetch --tags`, next free number, master CI green, nightly services
  inactive, outside 01:00-04:00 UTC; `gh pr merge`, `git tag`, `git push origin vX` each alone.
- Prod read-only unless the owner says yes for that action; `export APP_IMAGE=$(cat .last_deploy_image)`
  before `docker compose run`; container API checks via `docker exec ai-news-app python -c ...`.
- A covered file changed without its code doc fails CI (`check_code_docs.py --diff --strict`):
  update the doc that covers it (e.g. `scripts/run_daily_digest_job.sh` -> `core/daily/enrichment.md`).
- Archive this prompt to `docs/archive/2026-10/` in your first docs PR.
