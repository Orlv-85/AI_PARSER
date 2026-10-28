# Period AI Signals (weekly)

Feature 017 (`specs/017-weekly-monthly-signals/`). Weekly sums and comparisons of the stored daily
signals. Everything is computed from stored data: $0, no provider, page loads never call one. What it
computes and why: `src/app/core/periodic/signals_period.md`. This guide is for operators only.

State of the feature: numbers, command, nightly step and read API exist; the `/weekly` page, the paid
brief and the monthly view come in later releases. Readers see nothing yet.

## Enable

`AINEWS_PERIOD_SIGNALS_ENABLED` (default `false`) gates the command. Off: the command prints
`{"state": "disabled", ...}`, exits 0 and writes nothing. `docker-compose.prod.yml` passes the
variable from the server `.env` (default `false`). Set `AINEWS_PERIOD_SIGNALS_ENABLED=true` there to
turn on both manual runs and the nightly step in `scripts/run_daily_digest_job.sh`; with it unset
the nightly step logs `disabled` and does nothing.

After the deploy (the migration runs with `alembic upgrade head` in the deploy script and adds two
empty tables):

```bash
L="flock -w 7200 /tmp/ai-news-auto-update.lock"
C="docker compose -f docker-compose.prod.yml run --rm"

# backfill the first three weeks (2026-10-12, 10-19, 10-26), oldest first
$L $C app ai-news period-signals --backfill 3

# check what is stored
curl -s "http://127.0.0.1:8010/api/news/period-signals/index"
curl -s "http://127.0.0.1:8010/api/news/period-signals?kind=week&start=2026-10-19"
```

The run report is JSON: `state`, `written` (periods stored), `unchanged`, `periods` (status per
week), `skipped_before_first` (weeks before the first full comparable week; never computed).

## Commands

| Command | Does |
| --- | --- |
| `ai-news period-signals` | the latest completed week (a week ends on Sunday; from Monday it is complete) |
| `--backfill N` | N weeks ending at the target, oldest first |
| `--period YYYY-MM-DD` | the week that contains the date; it must be completed and not before the first week (exit 2 otherwise) |
| `--recompute-all` | every week from the first one |
| `--kind month` | reports `not_built`; monthly view is a later release |

A run stores a week only when its content changed (hash compare), so it is safe to run every night.

## Recompute

After a change of daily snapshots (entity merge, daily recompute) run
`ai-news period-signals --recompute-all`: only the weeks whose numbers changed are rewritten. After
a release that bumps `PERIOD_METHODOLOGY_VERSION` run the same command ($0).

## Rollback

- Stop the work: unset the flag (or leave it off). Pages and the API show `unavailable`.
- Remove the data: `docker compose -f docker-compose.prod.yml run --rm app alembic downgrade e7b4c2a9d150`
  drops `period_signal_reports` and `period_signal_briefs`; stored weeks are recomputable at $0.
