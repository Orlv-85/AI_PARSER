# src/app - overview

Entry points: CLI `ai-news` (`cli/main.py`), web app (`web/app.py`, launched by `scripts/run_web.sh`).
Production jobs: `scripts/run_daily_fetch_job.sh`, `scripts/run_daily_digest_job.sh`.

## Packages

| Package | Role |
| --- | --- |
| `cli/` | Typer commands: sources, fetch, serve, top, search, prune, daily-publish, daily-signals (+ entities), weekly-analytics, source candidates |
| `config/` | `settings.py` (env `AINEWS_*`), `sources.py` (`sources.yaml` loader) |
| `ingest/` | RSS/HTML fetching, page filtering, date evidence |
| `core/` | Domain logic. Shared: `models.py`, `categories.py`, `canonicalize.py`, `jev.py`, `provider_costs.py` (paid provider prices, dollar caps). Packages: `ingestion/` (pipeline, admission, scoring, dedup, `reject_policy.py` (conservative reject verdict)), `daily/` (digest enrichment, rubric, re-enrichment pilot, daily signals), `weekly/` (weekly analytics), `sources/` (source onboarding and review) |
| `storage/` | SQLAlchemy models (`models_sql.py`), repositories, Alembic migrations, ledgers and journals; `article_snapshot.py` (frozen table snapshots, article references); `journal_files.py` (canonical JSON, fingerprint, private atomic writes) |
| `web/` | FastAPI app, API models (`web/models.py`), HTML templates |
| `observability/` | Logging setup |

## Code docs

Feature docs live next to their main module and are checked by `scripts/check_code_docs.py`
(rule: AGENTS.md, "Feature Docs Next To Code").

| Feature | Doc |
| --- | --- |
| Daily AI Signals (006, 007) | `core/daily/signals.md` |
| Fetch pipeline (001, 002, admission) | `core/ingestion/pipeline.md` |
