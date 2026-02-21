# AI News Collector

Spec-driven Python application for collecting fresh English-language AI news from configured RSS/HTML sources.

## Requirements

- Python 3.12+
- SQLite (bundled with Python)
- `pip` or `uv`

## Installation

```bash
python -m venv venv1
source venv1/bin/activate
pip install -e ".[dev]"
```

## Configuration

### 1) Environment variables

```bash
export AINEWS_DATABASE_URL="sqlite:///./data/ai_news.db"
export AINEWS_SOURCES_PATH="sources.yaml"
export AINEWS_REQUEST_TIMEOUT_SECONDS="15"
export AINEWS_MAX_RETRIES="3"
export AINEWS_PER_SOURCE_MIN_INTERVAL_SECONDS="1.0"
export AINEWS_RESPECT_ROBOTS_TXT="true"
```

### 2) Source list (`sources.yaml`)

Project includes a starter `sources.yaml` with RSS + HTML sources.

Source schema:

- `id`
- `name`
- `type`: `rss` or `html`
- `url`
- `enabled`
- `fetch_interval_minutes`
- `source_weight`
- `html` (required for `type: html`)

## CLI Usage

### Show configured sources

```bash
ai-news sources
```

### Fetch once

```bash
ai-news fetch --once
```

### Top news

```bash
ai-news top --hours 24 --limit 30
```

### Search

```bash
ai-news search --query "gpt" --days 7
```

## What the MVP does

- Ingests RSS and HTML sources.
- Normalizes content into a unified article model.
- Canonicalizes URLs and prevents duplicate inserts by canonical hash.
- Scores articles with freshness + AI relevance heuristics.
- Stores data in SQLite via SQLAlchemy and Alembic migrations.
- Emits structured JSON logs for fetch runs.

## Development

```bash
ruff check .
pytest
```

## Troubleshooting

- `ModuleNotFoundError`: activate `venv1` and reinstall with `pip install -e ".[dev]"`.
- `sqlite3.OperationalError: unable to open database file`: create `data/` directory or fix `AINEWS_DATABASE_URL`.
- Empty `top` results: run `ai-news fetch --once` first and verify enabled sources in `sources.yaml`.
- Source fetch errors: check network access and source availability; fetch run logs include `source_id`, `stage`, `error_type`.

## Spec Artifacts

- `.specify/memory/constitution.md`
- `.specify/specs/001-ai-news-collector/spec.md`
- `.specify/specs/001-ai-news-collector/plan.md`
- `.specify/specs/001-ai-news-collector/tasks.md`
