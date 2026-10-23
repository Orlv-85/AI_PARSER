# Prompt: hold the digest while collection is paused; nightly health alert (2026-10-22)

You are the implementer for `/Users/vyacheslavorlovskiy/GitHub/AI_PARSER`. Read `AGENTS.md` first and
follow it. Work only in the worktree below; do not write to git in the main folder. Do not merge,
tag or touch prod.

## Incident and owner decision

- 2026-10-22: the nightly fetch (01:00 UTC) paused after 3 sources (Jev timeout, fixed in PR #82).
  The digest job (02:00 UTC, `scripts/run_daily_digest_job.sh` -> `ai-news daily-publish`) waited
  for the host lock, then published the 2026-10-21 digest with ONE article: `publish_day`
  (`src/app/core/daily/enrichment.py`) does not look at the collection pause.
- Owner decision 2026-10-22: in such a night the digest is published later but complete, not on
  time with one article.

## Decided by the coordinator (implement as written)

1. `publish_day` checks `read_collection_status` (`src/app/storage/admission.py`) first. If
   collection is paused, it makes no paid call, keeps the previous digest, and returns a report with
   `state="held_collection_paused"` (report.json written as usual). `daily-publish` exits with code
   2 for that state (1 stays "failed_preserved_previous"), so the job shell sees it.
2. Catch-up: new option `ai-news daily-publish --catch-up`: publishes, oldest first, every day in
   the last `DAILY_CATCH_UP_DAYS = 3` completed UTC days (yesterday included) whose latest
   `data/daily-enrichment/<day>/report.json` has `state == "held_collection_paused"`, plus yesterday
   if it has no report yet. Collection still paused -> each such day stays held. Without the option
   the command is unchanged (one day).
3. `scripts/run_daily_digest_job.sh`: on exit code 2 from `daily-publish` it prints
   `daily-publish held: collection paused` to stderr, skips daily-signals and exits 0 (a held
   day is not a failed job). Then a new mode `scripts/run_daily_digest_job.sh --catch-up` (same
   lock, same budget) runs `daily-publish --catch-up` and daily-signals for every day it published.
4. `scripts/run_daily_fetch_job.sh`: replace the final `exec flock ...` with the same `flock`
   command without `exec`, keep its exit status; after a successful fetch (exit 0), run
   `sh "$SCRIPT_DIR/run_daily_digest_job.sh" --catch-up` only if some report.json in the last
   `DAILY_CATCH_UP_DAYS` days says `held_collection_paused` (a cheap shell check, e.g.
   `grep -l '"state": "held_collection_paused"' data/daily-enrichment/*/report.json`; match the exact
   JSON spacing `private_write` produces). The fetch job's own exit status is returned. No timer,
   port, retention or auth change.

5. Nightly health alert (owner yes 2026-10-22: "know when the night broke"). The fetch and digest
   run as systemd timers on the server, so GitHub never reports their failures. New workflow
   `.github/workflows/nightly-health.yml`:
   - `on: schedule: cron "0 3 * * *"` (03:00 UTC: fetch starts 01:00, digest 02:00) and
     `workflow_dispatch`; `permissions: contents: read`; one job, `timeout-minutes: 10`.
   - SSH exactly like `.github/workflows/db-maintenance.yml` (same secrets and env names:
     `SERVER_PASSWORD`, `DEPLOY_USER`, `DEPLOY_HOST`, `DEPLOY_APP_DIR`, sshpass,
     `StrictHostKeyChecking=accept-new`). Read-only commands only: no restart, no write.
   - The checks run inline over ssh (do not depend on a script being present on the server) and
     print one line per check; the job fails if any check fails:
     a) collection not paused: `docker exec ai-news-app python -c` with
        `read_collection_status` (from `app.storage.admission`, session from `app.storage.db.SessionLocal`);
     b) a `fetch_run_finished` line with today's UTC date in `logs/daily-fetch.log`;
     c) `data/daily-enrichment/<yesterday>/report.json` exists, `state` starts with `published`,
        and `scope_count >= MIN_DIGEST_SCOPE` with `MIN_DIGEST_SCOPE=5` (decided 2026-10-22
        (agent): scope 2026-10-10..20 was 11-100, weekends 17; the broken night had 1). With rule 1
        in place, `held_collection_paused` also fails this check (that is wanted: someone must know).
   - Document the workflow in `docs/` where operator commands for the nightly jobs live (find the
     runbook that mentions `run_daily_digest_job.sh`; add a short section: what it checks, how to
     run it by hand: `gh workflow run nightly-health.yml`). Note there: GitHub mails failures of a
     scheduled workflow to the user who last changed its cron line.
   - Test: `bash -n` cannot check YAML; add a small unit test that loads the YAML (PyYAML is a
     dependency if `sources.yaml` is parsed with it; check) and asserts the cron, the read-only
     permission and that no step runs `systemctl`, `docker compose run`, `rm` or `restart`.

## Setup

```
cd /Users/vyacheslavorlovskiy/GitHub/AI_PARSER
git fetch origin
git worktree add ../AI_PARSER-wt-digest-hold -b fix/digest-waits-for-collection-20261022 origin/master
cd ../AI_PARSER-wt-digest-hold
```

Checks in the worktree: `PYTHONPATH=src ../AI_PARSER/venv1/bin/python ...`,
`PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest ...`.

## Steps (doc first)

1. Create the code doc `src/app/core/daily/enrichment.md` (daily enrichment has none yet; AGENTS.md
   "Feature Docs Next To Code"; format like `src/app/core/daily/signals.md`). Header `module:
   src/app/core/daily/enrichment.py`, `covers:` `src/app/core/daily/enrichment.py`,
   `scripts/run_daily_digest_job.sh`, `scripts/run_daily_fetch_job.sh`. Keep it short: Behavior
   (scope by `day_articles`, reuse, paid work through `PilotJournal` with `TRANSPORT_REVIEW_REASON`,
   atomic publication with backup, the new hold and catch-up rules), each rule with `Tests: ...`
   naming existing tests in `tests/unit/test_daily_enrichment.py` / `tests/unit/test_deepseek_digest.py`
   and the new ones; a rule without a test says so. Decisions (the owner decision above, with date);
   Invariants; Code map; Tests. Add the docstring line naming the doc to `enrichment.py`, register
   the doc in `docs/README.md`, `README.md` and `src/app/README.md` like the other code docs.
2. Code: rules 1-5 above. Keep the existing behavior of every other path.
3. Tests:
   - `tests/unit/test_daily_enrichment.py`: `test_paused_collection_holds_day_without_paid_calls`
     (pause set -> `held_collection_paused`, no HTTP request, previous digest unchanged);
     `test_catch_up_publishes_held_days_oldest_first` (two held days, collection unpaused -> both
     published, oldest first); `test_catch_up_keeps_days_held_while_paused`;
     `test_catch_up_ignores_days_older_than_limit`.
   - CLI: `daily-publish` exit code 2 for the held state (find where `daily_publish` is tested; add
     it there).
   - `tests/unit/test_deepseek_digest.py` (it already fakes `docker` for the job script, see around
     line 326): `test_digest_job_held_skips_signals_and_exits_zero`;
     `test_digest_job_catch_up_runs_signals_for_each_published_day`.
   - A test for `run_daily_fetch_job.sh` in the same style: catch-up runs after a successful fetch
     when a held report exists; does not run when none exists or the fetch failed; the fetch exit
     status is kept.
4. `docs/troubleshooting.md`: case `digest-published-during-collection-pause` (symptom: digest of
   2026-10-21 had one article; cause; fix; verification = new test names).
5. Checks (all must pass, files ASCII):
   ```
   PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest tests/unit/test_daily_enrichment.py tests/unit/test_deepseek_digest.py tests/unit/test_code_docs.py
   PYTHONPATH=src ../AI_PARSER/venv1/bin/python scripts/check_code_docs.py --diff origin/master --strict
   bash -n scripts/*.sh
   PYTHONPATH=src ../AI_PARSER/venv1/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/nightly-health.yml'))"
   make lint PYTHON=../AI_PARSER/venv1/bin/python
   PYTHONPATH=src ../AI_PARSER/venv1/bin/pytest
   ```
6. Commit, push, PR:
   ```
   git add -A
   git commit -m "fix(daily): hold the digest while collection is paused and catch up after the next fetch" -m "On 2026-10-22 the digest of 2026-10-21 was published with one article because the fetch had paused. publish_day now holds the day while collection is paused; after the next successful fetch the held days (last 3) are published and their signals computed." -m "Co-Authored-By: <your model name> <noreply@anthropic.com>"
   git push -u origin fix/digest-waits-for-collection-20261022
   gh pr create --base master --head fix/digest-waits-for-collection-20261022 \
     --title "fix(daily): hold the digest while collection is paused, catch up after the next fetch" \
     --body "Incident 2026-10-22: the 2026-10-21 digest was published with one article during a collection pause. Owner decision: publish later but complete. publish_day returns held_collection_paused (exit 2) while paused; run_daily_digest_job.sh treats it as held (signals skipped, exit 0); run_daily_fetch_job.sh runs the digest job in --catch-up mode after a successful fetch when a held day exists (last 3 days). New read-only workflow nightly-health.yml (03:00 UTC) fails when collection is paused, today's fetch did not finish or yesterday's digest is missing or has scope < 5. New code doc src/app/core/daily/enrichment.md. Troubleshooting case added. Gate: make lint + full pytest (paste results)."
   ```
   Use your real model name in Co-Authored-By, or drop the line.

## Report (all fields required)

- PR link; branch; commit SHA; `git diff --stat origin/master`.
- Output tail of each check in step 5.
- Deviations from this prompt and why.
- Open questions, one line each (AGENTS.md "Owner And Questions").
