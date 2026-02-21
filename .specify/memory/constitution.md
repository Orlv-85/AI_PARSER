# Constitution — AI News Collector

## 1. Product principles
- Primary goal: deliver the freshest, English-language AI news with minimal duplicates.
- Freshness is more important than popularity.
- Prefer reliable sources and stable parsing methods (RSS first, HTML second).

## 2. Engineering principles
- Python 3.12+ only.
- Deterministic outputs: same inputs -> same stored objects (stable hashing and ranking).
- Fail-soft: one broken source must not stop the whole run.
- Respectful fetching: rate limiting per source, timeouts, retries with backoff.

## 3. Data principles
- Store canonical URL (strip tracking params).
- Store published_at in UTC; keep discovered_at in UTC.
- Deduplicate by URL + content similarity (simhash).
- Keep provenance: source_id and aliases for duplicates.

## 4. Quality gates
- ruff for linting, mypy optional (nice-to-have).
- pytest unit tests for canonicalization, scoring, dedup.
- Integration test: ingest fixtures -> persist -> query.
- No hard-coded secrets; config via env vars and YAML.

## 5. Observability
- JSON structured logs with run_id, source_id, stage, url, error_type.
- Log counters per run: fetched, parsed, new, duplicates, errors.

## 6. Delivery
- Provide CLI (Typer) as primary interface for MVP.
- README must include install, configure sources, run fetch, view top.
