# AI News Collector

Spec-driven Python application for collecting fresh English-language AI news from configured RSS/HTML sources.

## Requirements

- Python 3.14.x (project target)
- SQLite (bundled with Python)
- `pip` or `uv`

## Installation

```bash
python -m venv venv1
source venv1/bin/activate
pip install -e ".[dev]"
```

## Quick Start

```bash
ai-news sources            # show configured sources
ai-news fetch --once       # fetch once
ai-news top --hours 24 --limit 30
```

For an existing database, run `./venv1/bin/alembic upgrade head` first.

## What the MVP does

- Ingests RSS and HTML sources.
- Normalizes content into a unified article model.
- Canonicalizes URLs and prevents duplicate inserts by canonical hash.
- Scores articles with freshness + AI relevance heuristics.
- Stores data in SQLite via SQLAlchemy and Alembic migrations.
- Supports PostgreSQL in production with Alembic migrations.
- Emits structured JSON logs for fetch runs.

## Documentation

Index of all docs: [docs/README.md](docs/README.md). Code docs live next to the code:

- [System overview](src/app/README.md) - packages, entry points, list of code docs.
- [Daily digest enrichment](src/app/core/daily/enrichment.md) - publication, collection holds and catch-up.
- [Daily AI Signals](src/app/core/daily/signals.md) - behavior, decisions, invariants, code map.
- [Period AI Signals](src/app/core/periodic/signals_period.md) - weekly and monthly sums and comparisons: periods, status, coverage, decisions.
- [Fetch pipeline](src/app/core/ingestion/pipeline.md) - ingestion: sources, page filter, admission, scoring.
- [Source onboarding](src/app/core/sources/onboarding.md) - candidate import, check, review, approval into collection.
- [Article archive](src/app/core/archive/capture.md) - private archive of article text; prune archives before delete.
- [Web pages](src/app/web/pages.md) - pages, access, placeholders, static CSS/JS assets.

General:

- [Docker and production deploy](docs/deploy.md) - Docker, CI/CD, server setup, daily digest jobs, maintenance, systemd.
- [Configuration](docs/configuration.md) - environment variables, Jev admission, `sources.yaml` and source management.
- [CLI usage](docs/cli.md) - web onboarding, fetch/cron, rollout knobs, search, prune.
- [Article re-enrichment](docs/archive/2026-10/article-reenrichment.md) - archived implementation guide (re-enrichment finished 2026-10-11).
- [Daily AI Signals operator guide](docs/daily-signals.md) - operator commands, costs, rollback.
- [Troubleshooting](docs/troubleshooting.md) - known failures (flaky tests, local env) with causes and fixes.

## Publishing digests over HTTP (operators)

With web auth enabled, `POST /api/news/digests` and
`POST /api/news/weekly-analytics` require an admin session or
`Authorization: Bearer $AINEWS_PUBLISH_API_TOKEN`; reads stay public. The deploy
workflows write the token to the server `.env` from the repository secret
`AINEWS_PUBLISH_API_TOKEN`; give the same value to any machine publisher such as
`scripts/digest_generator.py`. See
[Configuration](docs/configuration.md#publish-api-token).

## Article dates and one-time re-enrichment

Publication, modification and discovery are separate. Unknown publication
timestamps are `null`; known calendar dates remain available without an invented
time. News APIs also expose publication status/precision and optional material
type/comparison metadata. Migration `a42b750d0c44` is required for these fields.

See [the implementation and operator guide](docs/archive/2026-10/article-reenrichment.md) for
the module map, API changes, private cache, provider journal, apply/restore and
the limits of daily automation. The ten re-enrichment topics are readable and
filterable; the ordinary JEV rubric and daily digest process remain separate.
The completed data operation is recorded in
[the production report](docs/archive/2026-10/reenrich-production-results-2026-10-11.md).

## Development

```bash
ruff check .
pytest
```

## Troubleshooting

See also [docs/troubleshooting.md](docs/troubleshooting.md) for known CI/test failures.

- `ModuleNotFoundError`: activate `venv1` and reinstall with `pip install -e ".[dev]"`.
- `sqlite3.OperationalError: unable to open database file`: create `data/` directory or fix `AINEWS_DATABASE_URL`.
- Empty `top` results: run `ai-news fetch --once` first and verify enabled sources in `sources.yaml`.
- Source fetch errors: check network access and source availability; fetch run logs include `source_id`, `stage`, `error_type`.

## Spec Artifacts

- Feature specs: `specs/<NNN>-<name>/` (process and history); current behavior lives in the code
  docs next to the code (see `AGENTS.md`).
- Format of a new spec: `.specify/templates/`.
- `.specify/memory/constitution.md`: principles of the first version (history, partly outdated).
