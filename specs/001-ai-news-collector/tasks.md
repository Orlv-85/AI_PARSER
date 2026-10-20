# Tasks — AI News Collector (MVP)

## T1 Repo bootstrap
- Create Python project structure.
- Add pyproject (dependencies), ruff config, pytest config.
- Add README skeleton.

## T2 Config system
- Implement settings via env vars.
- Implement `sources.yaml` loader and validation (Pydantic).

## T3 Storage layer
- SQLAlchemy models: sources, articles, article_aliases, fetch_runs.
- Alembic init + first migration.
- Repos: upsert source, insert article, add alias, query top/search.

## T4 Canonicalization
- Implement canonical URL function.
- Unit tests with tracking params and edge cases.

## T5 RSS ingestion
- Implement RSS fetch+parse.
- Map RSS fields to normalized Article.
- Fixtures + unit test parsing.

## T6 HTML ingestion (min 2 sources)
- Implement HTML list fetch and item extraction (config-driven).
- Implement article text extraction via trafilatura/readability.
- Add graceful fallbacks.

## T7 Deduplication
- Implement simhash on normalized title (and optional lead).
- Implement merge logic (alias creation).
- Unit tests on near-duplicate titles.

## T8 Scoring & ranking
- Implement AI relevance heuristic + stop-words.
- Implement freshness score + rank_score formula.
- Unit tests for scoring behavior.

## T9 CLI
- Typer commands:
  - fetch --once
  - top --hours --limit
  - search --query --days
  - sources
- Output formatting.

## T10 Observability & reliability
- JSON logs with run_id/source_id/stage.
- Retry/backoff; per-source rate limit.
- Ensure failures don't stop the run.

## T11 Integration test
- Use saved RSS/HTML fixtures.
- Run pipeline ingest->persist->query top.
- Ensure deterministic ranking.

## T12 Documentation
- README: install, configure, run, examples, troubleshooting.
