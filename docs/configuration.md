# Configuration

## 1) Environment variables

```bash
export AINEWS_DATABASE_URL="sqlite:///./data/ai_news.db"
export AINEWS_SOURCES_PATH="sources.yaml"
export AINEWS_REQUEST_TIMEOUT_SECONDS="15"
export AINEWS_MAX_RETRIES="3"
export AINEWS_PER_SOURCE_MIN_INTERVAL_SECONDS="1.0"
export AINEWS_RESPECT_ROBOTS_TXT="true"
```

Optional Jev relevance scoring runs after RSS/HTML text extraction and before
article persistence. Set these values in the repository root's private `.env`
or export them in the process environment:

```dotenv
JEV_API_KEY=your-typesafe-api-key
AINEWS_JEV_ENABLED=true
AINEWS_JEV_MODEL=jev-1.13.0
AINEWS_JEV_TIMEOUT_SECONDS=3
AINEWS_JEV_CATEGORY_MIN_CONFIDENCE=0.7
```

The same Jev request returns relevance and a primary thematic category from the
seven existing digest sections. Jev's relevance probability feeds the existing
ranking formula. Categories are saved only when confidence meets
`AINEWS_JEV_CATEGORY_MIN_CONFIDENCE` (default `0.7`). Uncertain, unknown, or
invalid categories fall back to existing digest rules, independently of relevance.
It does not generate summaries or discard articles by default. Optional
semantic admission is gated by `AINEWS_SEMANTIC_ADMISSION_ENABLED=true` and
requires JEV. When enabled, AI-screening outages pause collection for the cycle,
and unchecked candidates remain available for retry. AI-central news, research,
substantive reviews, tutorials and evergreen guides
are eligible. Advertising landings, About pages, non-AI topics and incidental
AI mentions are excluded. Admission is categorical; category confidence and
ranking probability are independent and do not act as admission thresholds.
Already accepted articles persist; unchecked candidates remain in a durable
ledger, and never fall back to keyword admission. The exact public notice is:
`News collection is paused because AI screening is unavailable. Admin: please
check the AI providers and configuration.` Without semantic admission, existing
keyword scoring remains the default. If JEV is disabled or the API fails while
admission is enabled, no keyword fallback is used. After an API failure, no more
JEV calls are made during that fetch cycle; the next cycle retries pending work.
Pending work is replayed before checking the current feed/list, including after
a 304 response or list rotation. Up to 50 pending candidates per source are
replayed per cycle. Rejects and insufficient-evidence decisions are cached until
the sent evidence, model, policy or prompt version changes. The pause notice
clears after a fresh successful assessment; empty or cache-only retries retain it.
Apply the Alembic migration before enabling admission on an existing database.
Confirmed exclusions from the HTML page filter settle their pending URL and do
not replay after a 304. Temporary loading/parsing failures remain pending.
Connections and repeated-text results are reused within each cycle. Only bounded
title/summary/content text is sent. The key is masked in settings and is never
included in fallback logs.

Production Compose passes the Jev key and settings from the server's private
`.env` into the app container. Configure `JEV_API_KEY` privately on the server.
Both deploy workflows enforce `AINEWS_JEV_ENABLED=true` and
`AINEWS_SEMANTIC_ADMISSION_ENABLED=true`; production Compose defaults both to true.
Missing keys or screening outages pause collection without keyword admission.
The deployment applies migrations before starting the app. Local application
settings still default to disabled. Compose also forwards
`AINEWS_SEMANTIC_ADMISSION_POLICY_VERSION` and
`AINEWS_SEMANTIC_ADMISSION_PROMPT_VERSION`; their defaults match `Settings`.
Change the relevant version when changing admission policy or prompt.

Stored categories and confidence are included in `/api/news`, the digest link
feed and exports when available. The news page supports filtering by category
and `sort=category` (existing category order, then rank and freshness).
Digest generation uses the stored category first, with keyword rules for old or
unclassified articles, and ranks articles inside each group. A failed or disabled
Jev run does not erase previously accepted categories. Old articles are not
automatically reclassified and existing published digests are not rewritten.

For an existing database, apply the additive migration before starting this code:

```bash
./venv1/bin/alembic upgrade head
```

To keep local tests independent of a configured live API, run them with
`AINEWS_JEV_ENABLED=false ./venv1/bin/pytest`.

Daily AI Signals (feature 006) extract entities and events per digest article with one
DeepSeek call each, after `daily-publish`. Paid extraction is off by default; the owner
enables it in the server's private `.env`. Recompute-only runs and entity commands make no
provider calls and work with the flag off. Details: `docs/daily-signals.md`.

```dotenv
AINEWS_DAILY_SIGNALS_ENABLED=false          # gates paid extraction only
AINEWS_DAILY_SIGNALS_COMPARABLE_FROM=2026-10-10  # earlier digests are history-only evidence
AINEWS_DAILY_SIGNALS_MAX_CALLS=200          # physical provider calls per run
AINEWS_DAILY_SIGNALS_MAX_SECONDS=2700       # app-side wall limit per run
AINEWS_DAILY_SIGNALS_MAX_USD=0.50           # spend cap per run, checked before every call
```

The key is the existing `DS_API_KEY`. The CLI flags `--max-calls`, `--max-seconds` and
`--max-usd` override the caps for one invocation. Bounds: calls 1-5000, seconds 60-14400.

In production (`docker-compose.prod.yml`) only `AINEWS_DAILY_SIGNALS_ENABLED` is passed to the
container; the other four settings keep their defaults there, so use the CLI flags for caps.

### Publish API token

When web auth is enabled, the public API paths `/api/news/digests`,
`/api/news/daily-signals` and `/api/news/weekly-analytics` are public for
`GET`/`HEAD` only. Every other
method on any `/api/` path (except `/api/auth/login` and `/api/auth/logout`)
requires authentication. Writes accept either a valid admin session cookie or,
for machine publishers, a bearer token:

```dotenv
AINEWS_PUBLISH_API_TOKEN=<openssl rand -hex 32>
```

- The token must be at least 32 characters; an empty value disables bearer auth.
- It is accepted only for `POST /api/news/digests` and
  `POST /api/news/weekly-analytics`, not for other admin APIs.
- `scripts/digest_generator.py` sends `Authorization: Bearer <token>` on every
  POST to the app when `AINEWS_PUBLISH_API_TOKEN` is set in its environment.
  `scripts/run_weekly_analytics_job.sh` reads the token from the app container
  when it is not exported.
- With auth disabled (local dev), writes stay open as before.
- In production the deploy workflows write the value from the repository secret
  `AINEWS_PUBLISH_API_TOKEN` into the server `.env` (see [deploy](deploy.md)).

## 2) Source list (`sources.yaml`)

Project includes a starter `sources.yaml` with RSS + HTML sources.

Source management model:
- The database is the primary operational source registry.
- `sources.yaml` is a bootstrap/import artifact and an optional deterministic export snapshot.
- Runtime onboarding/review should happen against DB-backed records; YAML remains useful for seed data, backups, and diffs.

Phase 4 interop helper commands:

```bash
python scripts/sources_onboarding_helper.py db-bootstrap --sources sources.yaml
python scripts/sources_onboarding_helper.py db-review --status draft
python scripts/sources_onboarding_helper.py db-validate --batch-id 1
python scripts/sources_onboarding_helper.py db-export --output tmp/approved_sources.snapshot.yaml
```

Source schema:

- `id`
- `name`
- `type`: `rss` or `html`
- `url`
- `enabled`
- `fetch_interval_minutes`
- `source_weight`
- `html` (required for `type: html`)
