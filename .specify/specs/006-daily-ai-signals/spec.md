# Feature Specification: Daily AI Signals on the Main Page

**Feature Branch**: `006-daily-ai-signals`
**Created**: 2026-10-17
**Status**: Draft (direction agreed with the owner; plan and tasks to be produced by the implementing session)
**Input**: Owner request (RU, paraphrased): "Analytics does not really work. News volume per day has grown noticeably. Start with daily analytics on the main news page: what is new (new models, new kinds of AI, new companies), what became more popular, what is cooling down. Weekly and monthly later. Analytics should help me stay on top of a fast-moving industry, especially new things, and be useful for technical and investment-style decisions."

## Problem Context

### What exists today

- `/` renders the public daily digest (`src/app/web/digest.html`) for the previous UTC day by default.
  Items are grouped by `REENRICH_TOPIC_ORDER` (`src/app/core/categories.py`).
- Daily volume after semantic admission (live site, `GET /api/news/digests?date=`):
  2026-10-12: 56 items, 2026-10-14: 73, 2026-10-15: 92, 2026-10-16: 58. Earlier history is thinner
  (2026-10-10: 7 items), so baselines must tolerate short history.
- Daily publication (`ai-news daily-publish`, `src/app/core/daily_enrichment.py`) already calls
  JEV (admission, relevance, topic) and DeepSeek (grounded summary, `compared_products`) per article
  and stores results on `Article` (`summary`, `category`, `material_type`, `compared_products`,
  `enrichment_provenance`). Systemd timers run fetch and digest jobs daily in UTC
  (`scripts/install_daily_timers.sh`, `scripts/run_daily_digest_job.sh`).
- Below the digest the page shows a "Weekly AI Analytics" preview (New / Trending Up / Trending Down),
  fed by `GET /api/news/weekly-analytics`.

### Why the current analytics does not help

1. The live weekly endpoint returns `status: legacy` reports. Their "New" and "Trending Down" lists are
   individual article titles, not trends; non-AI items leak in (e.g. "Amazon's colorful and sturdy new
   Kindles", "The rise, fall, and rise of portable MP3 players" listed as Trending Down for 2026-10-11).
2. The newer engine (`src/app/core/weekly_analytics.py`, `attention-v2.1`) measures shares of 25 frozen
   broad topics (`src/app/core/weekly_topics.py`). Broad topics are present every week, so "New" can
   essentially never fire, and concrete novelties (a new model such as Reflection's Beam or Elorian's
   Glimpse) are absorbed into "Open-weight models" / "Multimodal models".
3. Its coverage gates (5+ publishers healthy 7/7 days, 90% classification, 100+ observations per week)
   mostly yield "Insufficient comparable source coverage."

The unit of analysis must change from "broad topic share" to **concrete things** (entities: models,
companies, products, technologies) and **what happened** (event types), computed per day.

## Goals

- G1. Every published day shows a compact "Daily AI Signals" block at the top of `/` that answers, in
  under a minute of reading: what is new, what is the biggest news, what is gaining attention, what is
  cooling.
- G2. "New" surfaces genuinely first-seen entities (models, products, companies, technologies).
- G3. Signals are explainable: each item links to the supporting articles and shows its counts.
- G4. The block degrades gracefully (partial data, short history) instead of showing an empty wall.
- G5. The data layer (per-article entities + event types) is reusable for later weekly/monthly analytics.

## Non-Goals (this spec)

- Rewriting weekly or monthly analytics (follow-up spec reuses this data layer).
- Watchlists, alerts, personalization, sentiment, stock prices or market data.
- Changing digest grouping, admission rules, fetch behavior, auth, ports, or deploy defaults beyond
  adding the signals step to the daily job.
- Removing the weekly preview; it may be moved below the digest or reduced to a link (see FR-012).

## User Scenarios & Testing

### User Story 1 - See what is new today (Priority: P1)

As a reader, I open `/` and immediately see which models, products, companies and technologies
appeared for the first time in the corpus on the digest date.

**Independent Test**: Seed history where entity "Beam" (type `model`, vendor "Reflection AI") never
appeared before D and appears in 2 sources on D; the block lists it under New with type, vendor, source
count and links.

**Acceptance Scenarios**:
1. Given an entity first seen on D in >= 2 distinct sources, then it is listed under New as confirmed.
2. Given an entity first seen on D in exactly 1 source, then it is listed as an "early signal" (visibly
   distinct, ranked below confirmed items), or hidden if the list is already full.
3. Given an entity seen before D under an alias (e.g. "GPT-6 Astra" vs a known "GPT-6" family), then it
   is not reported as New if the alias resolves to an existing canonical entity.
4. Given available history before D is shorter than the novelty lookback, then New is still shown with
   a note "history: N days" so the reader knows novelty is relative to N days.

### User Story 2 - See the top stories of the day (Priority: P1)

As a reader, I see the 3-5 stories that the most distinct sources covered on D, each as one line with
a source count, linking to the articles.

**Acceptance Scenarios**:
1. Given 6 articles from 5 publishers about the same event, then they form one story with count 5,
   not 6 separate entries.
2. Given ties, then stories are ordered by distinct publishers, then article count, then earliest time.

### User Story 3 - See what is rising and cooling (Priority: P1 for rising, P2 for cooling)

As a reader, I see entities and technologies whose attention grew or fell, using a rolling window that
is stable day to day.

**Acceptance Scenarios**:
1. Rising: mentions in the 7 days ending D vs the previous 7 days meet minimum count and growth
   thresholds (defaults in FR-008). Each item shows both counts.
2. Spike: an entity with an unusually high count on D vs its trailing daily average is marked as a
   spike, even if the 7-day comparison is not yet decisive.
3. Cooling: symmetric decline with minimum previous-window support; rendered as a secondary, collapsed
   or shorter list because single-day declines are mostly noise.
4. Given fewer than 14 days of history, then Rising/Cooling show a "baseline building" note and only
   items that still meet the minimum counts.

### User Story 4 - Know what kind of events happened (Priority: P2)

As a reader, I see counters by event type for D (e.g. "4 model releases, 2 funding rounds,
1 acquisition, 3 regulation") and can click one to filter the digest or the signals list.

## Requirements

### Functional Requirements

- **FR-001 Input scope**: Signals for date D use only articles that are part of the published digest
  for D (same scope as `digest_groups` / `reusable` in `daily_enrichment.py`), so non-AI and
  non-admitted items never enter analytics. History uses the same rule per day.
- **FR-002 Per-article extraction**: For each in-scope article, store a versioned extraction with:
  - `entities`: up to ~8 items, each `{name (source spelling), canonical_name, type, vendor|null,
    role: primary|mentioned}`; `type` in `model, product, company, person, technology, benchmark,
    dataset, other`.
  - `event_type`: one of `model_release, product_launch, funding, acquisition, partnership,
    research, benchmark_result, regulation_policy, legal, security_incident, infrastructure_deal,
    hardware, people_move, opinion_analysis, other`.
  - `novelty_claim`: boolean, the article itself presents something as newly released/announced.
  Extraction must be grounded in the article text only (same untrusted-input rules as existing prompts),
  cached by article content hash + extraction version, and reuse existing provider settings and keys.
- **FR-003 Entity resolution**: Maintain a canonical entity registry with aliases. Resolution order:
  exact normalized key -> known alias -> conservative fuzzy/LLM match within the same type and vendor.
  When unsure, create a new entity (a duplicate New is preferable to hiding a real novelty) and record
  the decision for later merge. Provide an operator path (CLI is enough) to merge two entities.
- **FR-004 First seen**: Each canonical entity stores `first_seen_day` (earliest in-scope article day).
  Backfill must recompute it from stored history, not only from the run date forward.
- **FR-005 Story clustering**: Group in-scope articles of D into stories. Deterministic first:
  shared primary entity + same event type, plus title similarity (`dedup.simhash64` exists). An LLM
  tie-break is allowed but optional and cached. Story label = the clearest article title or a short
  generated label grounded in member titles.
- **FR-006 Daily snapshot**: Compute a deterministic snapshot per D from stored extractions and store it
  (versioned, re-computable, idempotent upsert per date). Rendering never calls providers.
- **FR-007 Sections**: `new` (max 8), `top_stories` (max 5), `rising` (max 6, with spike flag),
  `cooling` (max 4), `event_counts` (all types with count > 0). Each item carries counts and up to 3
  supporting article links (distinct publishers first).
- **FR-008 Default thresholds** (configurable, recorded in the snapshot):
  - New: lookback = all available history, minimum 30 days required to drop the "history" note;
    confirmed at >= 2 distinct publishers, early signal at 1.
  - Rising: current 7d mentions >= 4, growth >= +50%, absolute delta >= 3 distinct articles.
  - Spike: count on D >= 3 and >= 3x the trailing 7-day daily mean.
  - Cooling: previous 7d mentions >= 5, decline <= -50%, absolute delta >= 3.
  - Mentions count distinct articles (one per article per entity); also report distinct publishers.
  The implementing session should tune these on real history and document the chosen values.
- **FR-009 Status, not walls**: Snapshot has `status` in `ready | partial | building_history |
  unavailable` plus per-section notes. `partial` when some in-scope articles failed extraction (show
  coverage "extracted 61/64"). The block never replaces content with a generic insufficiency message
  when it has anything to show.
- **FR-010 API**: Public `GET /api/news/daily-signals?date=YYYY-MM-DD` returns the stored snapshot
  (404-free: return `status: unavailable` with an empty body shape when missing). Response model added
  to `src/app/web/models.py`. Must be listed among public routes the same way `/api/news/digests` is.
- **FR-011 Job and CLI**: `ai-news daily-signals --report-date D` (extract missing + compute snapshot)
  and `--backfill-days N` (extract and recompute history oldest-first). Bounded paid work: per-run call
  cap and wall-clock cap, resumable. The daily digest job runs signals after a successful
  `daily-publish`; a signals failure must not fail or roll back the published digest.
- **FR-012 Main page UI**: In `digest.html`, render a "Daily AI Signals" block directly under the hero /
  date picker and above digest groups:
  - Row 1: event-type chips with counts (US4).
  - Card grid: New | Top stories | Rising (with spike badge) ; Cooling as a smaller card or collapsible.
  - Each item: name, type/vendor tag, counts (e.g. "3 sources", "7d: 2 -> 9"), expandable links.
  - Status line for partial/building_history.
  - Mobile: cards stack, no horizontal scroll. Match existing visual style and escaping (`escapeHtml`).
  - The existing Weekly preview moves below the digest groups (or becomes a link) without changing its
    API contract.
- **FR-013 Backward compatibility**: Existing endpoints, digest storage, weekly tables and CLI commands
  stay unchanged. New tables via Alembic migration only; SQLite and PostgreSQL both supported.

### Key Entities

- **ArticleSignal**: article_id, extraction_version, content_hash, event_type, novelty_claim, payload
  JSON, provider provenance, status (`ok | failed | skipped`), timestamps.
- **AIEntity**: id, canonical_name, normalized_key, type, vendor, first_seen_day, created_at.
- **AIEntityAlias**: entity_id, alias, normalized_alias, source (`extraction | merge | manual`).
- **ArticleEntity**: article_id, entity_id, role, surface_name.
- **DailySignalReport**: report_date (unique), version, status, thresholds JSON, payload JSON
  (sections), coverage stats, created_at/updated_at.

Exact table and column names are the implementing session's choice; keep naming consistent with
`models_sql.py`.

## Edge Cases

- Day with very few items (e.g. 7): sections may be short; status `ready` with small counts is fine.
- Entity mentioned only in passing in many listicles: `role: mentioned` counts for Rising but New
  requires at least one article where the entity is `primary` or `novelty_claim` is true.
- Generic terms ("AI", "LLM", "agents") must not become entities; extraction prompt and a stoplist
  should prevent this.
- Vendor names vs products (OpenAI vs ChatGPT vs GPT-6): distinct entities with type + vendor link.
- Re-running for the same D after late articles were published: snapshot recomputed, upsert.
- Extraction version bump: old rows remain readable; recompute is explicit (backfill), never implicit
  on page load.
- Provider outage: digest publishes as before; signals status `unavailable` or `partial`.

## Success Criteria

- SC-001: For each of 2026-10-12, 2026-10-14, 2026-10-15, 2026-10-16 (after backfill), New contains
  only concrete entities (no generic terms, no non-AI items) on manual review of all listed items.
- SC-002: Reflection "Beam" appears under New (or early signal) on its first day in the corpus.
- SC-003: Top stories never list two entries for the same event on the reviewed days.
- SC-004: `/` renders the block for a date with a snapshot and a clean status line without one;
  page load makes no provider calls.
- SC-005: Daily extraction cost is bounded and logged (calls, tokens) per run; typical day <= one
  provider call per in-scope article.
- SC-006: Repo-wide gate passes: `make lint PYTHON=./venv1/bin/python` and `./venv1/bin/pytest`.

## Open Questions (implementing session proposes, owner decides)

1. Store extraction in a new provider call vs extend the existing DeepSeek summary call (cheaper, but
   changes a pinned prompt/version used by daily publication). Default: separate call, separate version.
2. UI language: site UI is English today. Default: keep English.
3. Whether Cooling is shown daily at all or only from 14+ days of history.
4. Whether event-type chips filter the digest list (client-side) in this iteration or later.
