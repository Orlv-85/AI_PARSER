# Prompt: 017 release R4, weekly and monthly brief (T030-T031) (2026-10-28)

You are the **implementer** (background agent, Sonnet) for the 017 coordinator. You did not write the
plan; follow it. One PR, do not merge, do not tag. Production is read-only for you; you make **no
paid provider call** (all provider tests use `httpx.MockTransport`). The paid dry run on prod (T032)
is done by the coordinator after deploy.

State: R2 (numbers), R3 (`/weekly`) and R5 (legacy weekly retired) are live (v0.1.134-136). Prod
stores weeks 2026-10-12 (`building_history`) and 2026-10-19 (`ready`). Owner answer Q2 (2026-10-28):
both briefs, built in one release; the weekly brief is turned on as soon as it ships; the monthly
brief runs from 2026-12-01. Month numbers do not exist yet (R6): build the brief generic over the
period kind, with month values (packet cap, sentence counts, per-brief cap) defined now, so R6 only
adds month numbers; a month brief is never attempted while no month row exists.

## Read first

`AGENTS.md`; `specs/017-weekly-monthly-signals/plan.md` ("Brief", "Cost", "Versions", "Rollout",
owner answers); `tasks.md` Phase 4; `src/app/core/periodic/signals_period.md`;
`src/app/core/daily/signals.md` (brief sections: packet, validation, recovery, ledger, caps, prices,
"Why" lines); `src/app/core/daily/signals_brief.py`; the daily brief run path in
`src/app/core/daily/signals.py` and `SignalsLedger` (`git grep -n "class SignalsLedger" src`);
`BRIEF_PRICES`; the daily brief tests (`git grep -ln "parse_brief\|MockTransport" tests/unit`);
`src/app/core/periodic/period_run.py`, `src/app/storage/period_signals.py` (the empty
`period_signal_briefs` table), `src/app/web/period_view.py`, `src/app/web/routes/period.py`.

## Scope: T030, T031

**T030.** Doc first: Behavior of the brief in `signals_period.md` (packet, validation, recovery,
cache by input hash, caps, cost, flag; tests per rule), Decisions, Versions (`PERIOD_BRIEF_VERSION`).
Parameterise the packet and `parse_brief` in `signals_brief.py` for sentence counts (week 4-6, month
5-8) **without changing daily behavior**: daily tests unchanged and passing; the daily brief prompt
and its input hash for the daily fixtures unchanged (prove it in the PR body like R2a did for
payload hashes). `core/periodic/period_brief.py`: packet from the stored period payload plus digest
titles and summaries of the top stories, capped at `PERIOD_PACKET_MAX_BYTES` (week 16,000, month
24,000), prompt, `PERIOD_BRIEF_VERSION`, input hash.

**T031.** Brief step under `AINEWS_PERIOD_SIGNALS_BRIEF_ENABLED` (default off) in `period_run.py`
and the CLI (`--with-brief`, `--max-usd`; default total `AINEWS_PERIOD_SIGNALS_MAX_USD` 0.10 per
run), through `SignalsLedger` with its own run id, per-brief cap (week $0.05, month $0.08; the
reservation per attempt is priced at the byte cap like 007 so the caps hold), unknown model in
`BRIEF_PRICES`: no call. One recovery attempt, then `invalid` and no brief; the same `input_hash`
is never paid twice (`ok` or `invalid`). Flag off or no key: no provider object is created. The
nightly step: the brief runs only when the flag is on and the period row is `ready` or
`building_history` and has no brief for its input hash. Pass the flag through
`docker-compose.prod.yml` exactly like R2b did for `AINEWS_PERIOD_SIGNALS_ENABLED`
(`${AINEWS_PERIOD_SIGNALS_BRIEF_ENABLED:-false}`) with a compose test; show the hunk. Page and API
show the brief: the API `brief` field gets the stored text with numbered source links; `/weekly`
shows it at the top of the week with the same AI note wording as the daily brief. Tests with
`MockTransport`: ok, invalid after one recovery, cached by hash (no second call), per-brief cap,
run cap (`--max-usd`), unpriced model, flag off creates no provider, page and API with and without
a brief, escaped brief text and http(s)-only links. Operator doc `docs/period-signals.md`: enable,
dry run (`--with-brief --max-usd 0.05 --period 2026-10-19`), rollback.

## Rules

- Money: never exceed the plan's caps; any change of caps, model or prices goes to the owner
  (stop and report as yes/no with a recommendation).
- Do not change daily brief behavior, digest, fetch, deploy workflows; compose only the one line above.
- Unclear vs. code: decide, write "decided 2026-10-28 (agent): <reason>" in the doc, list it.
- Keep code ASCII; match the style of the daily brief code.

## Checks (from the worktree)

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER && git fetch -q && git worktree add -b feat/017-r4-period-brief ../AI_PARSER-wt-017r4 origin/master
cd ../AI_PARSER-wt-017r4
PYTHONPATH=src make lint PYTHON=../AI_PARSER/venv1/bin/python
PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest -p no:cacheprovider -o addopts="" | tail -1
../AI_PARSER/venv1/bin/python scripts/check_code_docs.py --diff origin/master --strict
bash -n scripts/*.sh
```

Use `PYTHONPATH=src`. No git writes in the main folder. No real provider calls (unset or fake keys
in tests).

## Commit and PR

Commit `feat(017): R4, weekly and monthly brief behind a flag` ending with
`Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`; add this prompt file at its path under
`specs/017-weekly-monthly-signals/records/`; push; `gh pr create --base master` with: what each task
added, daily-brief-unchanged proof, cost and caps as coded (reservation per attempt in $), compose
hunk, decided items, checks. Body ends with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Wait for CI
(`gh pr checks <N> --watch --interval 30`); fix real failures; do not call a CI failure "local only"
without proof.

## Report (final answer)

PR URL and SHA; CI result; files with line counts; daily-unchanged proof; caps and reservation in $;
exact operator commands for the dry run on 2026-10-19; decided items; full gate last line; anything
for the owner.
