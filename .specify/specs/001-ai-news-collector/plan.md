# Plan — AI News Collector

## 1. Architecture
Pipeline:
Fetch -> Parse -> Normalize -> Canonicalize -> Score -> Dedup/Cluster -> Persist -> Query

## 2. Modules
- app/config
  - settings.py (pydantic-settings)
  - sources.yaml loader
- app/ingest
  - fetcher.py (httpx client, retries, rate limit)
  - rss.py (feedparser)
  - html.py (httpx + trafilatura/readability)
- app/core
  - models.py (Pydantic)
  - canonicalize.py
  - dedup.py (simhash)
  - scoring.py
- app/storage
  - db.py (SQLAlchemy engine/session)
  - models_sql.py (tables)
  - repos.py (ArticleRepo, SourceRepo)
  - migrations (alembic)
- app/cli
  - main.py (Typer commands)
- tests/
  - unit/
  - integration/

## 3. Tech choices
- http: httpx
- RSS: feedparser
- text extraction: trafilatura (fallback readability-lxml)
- DB: SQLite (MVP), PostgreSQL later via DATABASE_URL
- CLI: Typer
- Logging: stdlib logging + JSON formatter
- Lint: ruff
- Tests: pytest

## 4. Data model (DB)
- sources
- articles
- article_aliases (article_id, source_id, url, discovered_at)
Key indexes:
- articles(published_at DESC)
- articles(rank_score DESC)
- articles(url_canonical_hash UNIQUE)

## 5. Run modes
- `fetch --once`: single run (cron-friendly)
- optional scheduler later (daemon mode)

## 6. Future roadmap (post-MVP)
- FastAPI read-only API
- LLM summaries (feature-flag)
- Topic clustering (agents/LLM/policy/hardware)
- UI
