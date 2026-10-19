# src/app - overview

Entry points: CLI `ai-news` (`cli/main.py`), web app (`web/app.py`, launched by `scripts/run_web.sh`),
MCP server (`mcp/server.py`). Production jobs: `scripts/run_daily_fetch_job.sh`,
`scripts/run_daily_digest_job.sh`.

## Packages

| Package | Role |
| --- | --- |
| `cli/` | Typer commands: sources, fetch, serve, mcp-serve, top, search, prune, daily-publish, daily-signals (+ entities), weekly-analytics, source candidates |
| `config/` | `settings.py` (env `AINEWS_*`), `sources.py` (`sources.yaml` loader) |
| `ingest/` | RSS/HTML fetching, page filtering, date evidence |
| `core/` | Domain logic: pipeline, admission, dedup, scoring, daily digest enrichment, weekly analytics, daily signals |
| `storage/` | SQLAlchemy models (`models_sql.py`), repositories, Alembic migrations, ledgers and journals |
| `web/` | FastAPI app, API models (`web/models.py`), HTML templates |
| `mcp/` | MCP server: news update and status tools for agents |
| `observability/` | Logging setup |

## Code docs

Feature docs live next to their main module and are checked by `scripts/check_code_docs.py`
(rule: AGENTS.md, "Feature Docs Next To Code").

| Feature | Doc |
| --- | --- |
| Daily AI Signals (006, 007) | `core/daily_signals.md` |
