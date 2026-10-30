# Period AI Signals (weekly and monthly)

Feature 017 (`specs/017-weekly-monthly-signals/`). Weekly and monthly sums and comparisons of the stored daily
signals. Everything is computed from stored data: $0, no provider, page loads never call one. What it
computes and why: `src/app/core/periodic/signals_period.md`. This guide is for operators only.

State of the feature: numbers, command, nightly step, read API, the `/weekly` and `/monthly` pages
and the paid brief exist for weeks and months. The numbers cost $0. The brief is the only
paid step and is off by default.

## Enable

`AINEWS_PERIOD_SIGNALS_ENABLED` (default `false`) gates the command. Off: the command prints
`{"state": "disabled", ...}`, exits 0 and writes nothing. `docker-compose.prod.yml` passes the
variable from the server `.env` (default `false`). Set `AINEWS_PERIOD_SIGNALS_ENABLED=true` there to
turn on both manual runs and the nightly step in `scripts/run_daily_digest_job.sh`; with it unset
the nightly step logs `disabled` and does nothing.

After the deploy (the migration runs with `alembic upgrade head` in the deploy script and adds two
empty tables):

```bash
cd /opt/ai-news
export APP_IMAGE="$(cat .last_deploy_image)"  # the released image; without it compose runs a stale :latest
L="flock -w 7200 /tmp/ai-news-auto-update.lock"
C="docker compose -f docker-compose.prod.yml run --rm"

# backfill the last three completed weeks, oldest first (on 2026-10-28 this stored 10-12 and
# 10-19; 10-05 is before the first computable week and skipped; 10-26 is computed by the
# nightly step from Monday 2026-11-02)
$L $C app ai-news period-signals --backfill 3

# check what is stored
curl -s "http://127.0.0.1:8010/api/news/period-signals/index"
curl -s "http://127.0.0.1:8010/api/news/period-signals?kind=week&start=2026-10-19"
```

The run report is JSON: `state`, `written` (periods stored), `unchanged`, `periods` (status per
week), `skipped_before_first` (weeks before the first full comparable week; never computed).

## Months

The same command and the same two flags. A month is a calendar month (UTC), computed only when it
is complete. The first month is November 2026: October 2026 is partial (data from 2026-10-12) and is
never computed. The nightly step runs the plain command, which now also takes the latest completed
month: before 2026-12-01 it does nothing and writes nothing; on 2026-12-01 it stores November
(`building_history`: there is no October to compare with, so no comparison and no risers) and, with
the brief flag on, writes its brief (one call, about $0.015-0.03, hard cap $0.08; a payload that
changes later on the same month is a new input and is briefed again, at the same cost). The first
month with a comparison is December 2026 (stored on 2027-01-01). Nothing else needs switching.

```bash
# on or after 2026-12-01: check the month, or compute it by hand
$L $C app ai-news period-signals --kind month
curl -s "http://127.0.0.1:8010/api/news/period-signals?kind=month"
# one month, by hand; --period is any day of a completed month; no brief unless --with-brief
$L $C app ai-news period-signals --kind month --period 2026-11-15
```

`/monthly` (and `/monthly?month=2026-11`) shows the stored month; the "Monthly" link appears on `/`
and `/weekly` once a month row exists.

## Brief (paid)

One short AI-written brief per week, shown at the top of `/weekly` and in the API `brief` field.
Rules and caps: `src/app/core/periodic/signals_period.md` ("Brief"). In short: one DeepSeek call per
brief (a second only to correct a rejected answer), about $0.005-0.01 for a week, hard caps $0.05 per
brief and `--max-usd` (default 0.10) per run; the same input is never paid twice.

Enable (needs `AINEWS_PERIOD_SIGNALS_ENABLED=true`, `DS_API_KEY` in the server `.env`):

```bash
# server .env
AINEWS_PERIOD_SIGNALS_BRIEF_ENABLED=true
```

From then on the nightly step writes the brief of the latest completed week once, on the first night
after the week is stored (later nights find the same input and pay nothing). `docker-compose.prod.yml`
passes the variable (default `false`); with it unset nothing paid ever runs and no provider object is
created.

Dry run on one stored week, before enabling (cost-capped; the flag must be on for this run, so set it
for the command only):

```bash
cd /opt/ai-news
export APP_IMAGE="$(cat .last_deploy_image)"  # the released image; without it compose runs a stale :latest
L="flock -w 7200 /tmp/ai-news-auto-update.lock"
C="docker compose -f docker-compose.prod.yml run --rm"
$L $C -e AINEWS_PERIOD_SIGNALS_BRIEF_ENABLED=true app \
  ai-news period-signals --period 2026-10-19 --with-brief --max-usd 0.05
```

The report has `brief.periods` (per week: `ok`, `invalid`, `cached` or `skipped:<reason>`),
`brief.run` (calls and USD actually spent) and `brief.terminal_reason`. `invalid` means the answer
failed validation twice: no brief is shown and the same input is not paid again; a new input (changed
numbers or a new `PERIOD_BRIEF_VERSION`) tries again. Paid backfill of older weeks:
`--backfill 3 --with-brief --max-usd 0.10`.

Check: `curl -s "http://127.0.0.1:8010/api/news/period-signals?kind=week&start=2026-10-19"` (the
`brief` field) and `/weekly`.

## Commands

| Command | Does |
| --- | --- |
| `ai-news period-signals` | the latest completed week (a week ends on Sunday; from Monday it is complete) and, in the same run, the latest completed month (the report has a `month` key) |
| `--kind week` / `--kind month` | that kind alone |
| `--backfill N` | N periods (weeks or months) ending at the target, oldest first |
| `--period YYYY-MM-DD` | the week or month that contains the date; it must be completed and not before the first week (2026-10-12) or first month (2026-11-01) (exit 2 otherwise) |
| `--recompute-all` | every period of the kind from the first one (with no `--kind`: weeks only) |
| `--with-brief` | paid: also write the brief of every period of the run (needs the brief flag) |
| `--max-usd X` | total USD cap of the brief step for the run (default `AINEWS_PERIOD_SIGNALS_MAX_USD`, 0.10) |
| `--cache-dir DIR` | where the ledger file lives (default `data/period-signals`) |

A run stores a week only when its content changed (hash compare), so it is safe to run every night.

## Recompute

After a change of daily snapshots (entity merge, daily recompute) run
`ai-news period-signals --recompute-all`: only the weeks whose numbers changed are rewritten. After
a release that bumps `PERIOD_METHODOLOGY_VERSION` run the same command ($0).

## Rollback

- Stop the paid step: set `AINEWS_PERIOD_SIGNALS_BRIEF_ENABLED=false` (or unset it). Stored briefs
  stay and keep showing; nothing is called. To hide them, delete the rows:
  `DELETE FROM period_signal_briefs;` (briefs are regenerated only when the flag is on again, at
  the cost above).
- Stop the work: unset the flag (or leave it off). Pages and the API show `unavailable`.
- Remove the data: `docker compose -f docker-compose.prod.yml run --rm app alembic downgrade e7b4c2a9d150`
  drops `period_signal_reports` and `period_signal_briefs`; stored weeks are recomputable at $0.
