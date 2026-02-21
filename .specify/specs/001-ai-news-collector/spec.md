# Spec — AI News Collector (MVP)

## 1. Purpose
A Python application that collects the freshest English-language AI news from configured internet sources, normalizes data, deduplicates items, scores by freshness and AI relevance, persists results, and provides a query interface via CLI.

## 2. In scope (MVP)
- Sources:
  - RSS/Atom ingestion for most sources.
  - HTML ingestion for at least 2 sources (list + article extraction).
- Normalized Article model.
- Deduplication:
  - Canonical URL normalization.
  - Similarity-based dedup using simhash on title (and optionally lead/content).
  - Store aliases to keep provenance.
- Scoring & ranking:
  - AI relevance heuristic (keyword-based with stop-words to avoid false positives).
  - Freshness score based on published_at with exponential decay.
  - Rank score combining freshness + relevance + source weight + mild multi-source boost.
- Persistence:
  - SQLite via SQLAlchemy.
  - Alembic migrations.
- CLI (Typer):
  - fetch (once)
  - top (hours, limit, optional tag/filter)
  - search (query, days)
  - sources (list enabled sources)
- Reliability:
  - timeouts, retries with backoff
  - per-source rate limiting
  - graceful error handling
- Observability:
  - structured JSON logs
  - per-run counters in logs

## 3. Out of scope (MVP)
- Full-site crawling / search engine behavior.
- Video/YouTube ingestion.
- Multi-user personalization.
- Complex ML ranking model.
- Mandatory LLM summaries (optional feature flag later).

## 4. Functional requirements
### FR-1 Source config
- Maintain a `sources.yaml` with:
  - id, name, type (rss|html), url
  - enabled, fetch_interval_minutes, source_weight
  - html options: list selectors, article selectors, or extraction strategy

### FR-2 Ingestion
- For each enabled source, fetch and parse:
  - list items with (title, url, published_at when available)
  - optionally full article text via extraction
- Normalize to Article schema.

### FR-3 Canonicalization
- Remove tracking parameters (utm_*, gclid, fbclid, etc.)
- Normalize host casing, strip fragments, normalize trailing slash.

### FR-4 Dedup
- If canonical URL already exists -> alias only.
- Else compare simhash with recent items (time window configurable).
- If similar above threshold -> merge as alias to existing cluster.

### FR-5 Scoring
- ai_relevance_score in [0,1] based on keyword weights:
  - higher weight in title, medium in summary, lower in content
- freshness_score in [0,1] based on age with half-life default 24h.
- rank_score = weighted sum:
  - freshness 0.6, relevance 0.3, source_weight 0.1 (+ small alias-count bonus)

### FR-6 Output
- CLI outputs items with:
  - title, source, published_at, rank_score, url
- Support filtering by hours/days and simple query terms.

## 5. Non-functional requirements
- 20 sources, 200–1000 items/day on a single machine.
- Parallelism limited (5–10 concurrent requests).
- Each run finishes within minutes under normal conditions.
- Respect robots.txt for HTML sources when enabled.

## 6. Acceptance criteria
- Re-running fetch does not create duplicate rows for same content.
- `top --hours 24 --limit 30` returns sorted items, non-empty if sources provide data.
- Dedup merges same story across multiple sources (at least via URL canonicalization).
- Unit tests cover canonicalization/dedup/scoring; integration test passes.
