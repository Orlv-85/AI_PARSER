# Prompt: coordinator, next session (2026-10-28)

You continue as the **coordinator** of `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. The owner
writes Russian; answer in Russian, short and plain. Previous coordinator: session `ai-parser-ba`.

## Read first (nothing else up front)

1. `AGENTS.md` and your memory files (`MEMORY.md` index).
2. From `origin/master` (`git fetch`; the main folder may lag): `docs/backlog/coordinator-todo.json`
   (the live todo list), `docs/work/coordinator-state-2026-10-24.json` (`new_rules_2026_10_24` and
   `state`), `owner_rules` of `docs/archive/2026-10/coordinator-state-2026-10-23.json`.
3. `specs/017-weekly-monthly-signals/plan.md` and `tasks.md` (the feature in progress).

## State on 2026-10-28

- Prod: **v0.1.132** (deployed 2026-10-27 23:45 UTC), green nights since. master `4538423` + docs PRs.
- Night of 10-28 checked: fetch/digest/archive green; admission pending 516 -> 72; new fetch log
  fields `examined_items`, `examined`, `sources_fetched` work; honest bot UA live in the container.
- Archive week (SC-002) checked 2026-10-28: coverage 95.7% (600/627), every day >= 91%, gave_up 0,
  no outage; 29 documents failed http_403 (22 openai.com, expected to give up); 4020 pending are
  the old 2026-10-24 seed and stay pending by design.
- SSH: key only, user `deploy` for CI and agents, root by key only, fail2ban on `/var/log/auth.log`,
  root password changed by the owner (lives only for the time4vps console).

## In flight

- **017 R1 = PR #130, merged and live as v0.1.133** (2026-10-28 12:30 UTC, deploy green). Checked
  after deploy: `ai-news --help` has no weekly command, no weekly cron for root or deploy.
  Baseline before the first night on v0.1.133: `weekly_input_observations` 7139 rows,
  `weekly_coverage_attempts` 2846. **Check on 2026-10-29:** both counts unchanged after the night;
  nightly jobs green. **Check on 2026-11-02 (Monday):** the legacy weekly report for 10-26..11-01
  is still created (`weekly_analytics_reports`). Agent's open point (decide yourself): dead
  plumbing `coverage_complete`, `acquisition_stopped`, HTML `quality_flags` still computed but
  unread - remove in a later cleanup.
- **Next: 017 R2** (numbers, tasks T010-...): write the implementer prompt to
  `specs/017-weekly-monthly-signals/records/prompt-r2-<date>.md` after reading `tasks.md` Phase 2;
  background Sonnet agent; review; owner yes to merge.
- Owner answers for 017 (2026-10-28): Q1 yes (retire legacy preview/pages later, delete v2), Q2 yes
  (weekly and monthly brief in one release; weekly brief on as soon as `/weekly` is live; monthly
  from 2026-12-01), Q3 yes (completed periods only), Q4 yes (month view last). R1 records them in
  `plan.md`. Then R2 numbers, R3 page, R4 briefs, R5 retire legacy, R6 month; each release after
  review of the previous one. Spec PRs and docs PRs you merge after green CI.

## First small task

DeepSeek docs PR (see "Executors"): in `coordinator-todo.json` mark ARCHIVE-week done (facts
above); FIREWALL note "owner 2026-10-28: later, current setup is safe enough"; add a small item
"daily-archive.log writes each nightly summary line twice"; set B2 to in_progress pointing to spec
017; archive `docs/work/prompt-todo-after-132-2026-10-28.md` and this prompt to
`docs/archive/2026-10/`.

## Executors and rules learned this session

- Code tasks: background subagent (Agent tool, model sonnet), prompt saved to a file first. A live
  peer session only when the owner names it (once a task went to the owner's own session).
- Simple docs tasks: DeepSeek, run by you:
  `ANTHROPIC_AUTH_TOKEN=<DS_API_KEY from .env> ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic ANTHROPIC_MODEL=deepseek-v4-pro ANTHROPIC_SMALL_FAST_MODEL=deepseek-v4-pro claude -p "Read and follow exactly <prompt file>" --allowedTools "Bash Read Write Edit" --max-turns 30`
  (unset ANTHROPIC_API_KEY, never print the key, run in background). Give it a Python edit script
  with asserts; dry-run the script on a `git archive` copy in the scratchpad first; then compare
  the PR files with the dry run byte for byte (`cmp`).
- Z.ai / GLM: dropped by the owner. Jev is a classifier, not an agent model.
- Verify every report yourself: diff, CI, full tests with a visible summary line
  (`pytest -p no:cacheprovider -o addopts="" | tail -1`; `-q` prints no summary here), a failing-
  before test where the agent claims one. Never wait with `until grep passed`.
- Subagents may be refused prod SELECTs; do read-only checks yourself.
- Allowed commands run alone: `gh pr merge N --merge`, `git tag -a vX <sha> -m ...`,
  `git push origin vX`. Before a tag: `git fetch --tags`, next free number, master CI green, nightly
  jobs inactive (`systemctl is-active ai-news-daily-{fetch,digest,archive}.service`), outside
  01:00-04:00 UTC.
- Prod read-only by default; `export APP_IMAGE=$(cat .last_deploy_image)` before
  `docker compose -f docker-compose.prod.yml run`.
- Prompts: `docs/work/prompt-*.md` (git-ignored) or `specs/<NNN>/records/`; archive when done.
