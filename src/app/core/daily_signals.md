<!-- code-doc
module: src/app/core/daily_signals.py
covers:
  - src/app/core/daily_signals*.py
  - src/app/storage/daily_signals*.py
  - src/app/storage/migrations/versions/*daily_signal*.py
  - src/app/web/signals_view.py
-->
# Daily AI Signals

The block at the top of `/` for one published digest day D: a short brief, what is new, which stories
several publishers covered, what is spiking or rising, what is cooling, and how many events of each
type happened. Everything is computed from stored data; page loads never call a provider.

This file is the intended current behavior of 006 (signals) and 007 (brief): change it first, then the
code and tests. `specs/006-daily-ai-signals/` and `specs/007-daily-signals-brief/` are the history of
how it got here. Operator commands, cost, rollback: `docs/daily-signals.md`.

## Behavior

**Scope and days**
- Only articles of the published digest of D count: digest items matched to articles by exact URL,
  then by canonical URL hash.
- A day is published when a digest row exists (it may have 0 items), missing otherwise; missing days
  never count as zero attention. Complete: no items, or at least 90% of digest items extracted.
- Digests before `AINEWS_DAILY_SIGNALS_COMPARABLE_FROM` (2026-10-10) are history only: they feed
  "first seen" but get no snapshot.
- Status of a day: `unavailable` (no snapshot, 0 items or nothing extracted), `partial` (day not
  complete), `building_history` (a section still waits for history), `ready`.

**Extraction and entities**
- One provider call per in-scope article: named entities with type, vendor, role and an "is new"
  judgment with a source quote, the main event type and a novelty flag. Names and quotes must occur in
  the article text; a quote that dates the release before the article clears "new". Cached per
  article, content hash and version.
- Input kinds (`input` in the extraction provenance): `full` (content of at least 300 characters),
  `title_summary` (title and RSS summary without HTML, at most 1,500 characters), `title_only`. A
  title-only article usually yields no entities but still counts as processed for day coverage.
- Every mention is stored as evidence that survives article retention. Entities are derived from all
  evidence by deterministic reconciliation plus operator overrides. Entities with conflicting vendors
  (`needs_review`) are excluded from New, Rising and spikes.

**Sections**
- **New**: an entity first seen in our corpus on D that an article of D presents as newly announced.
  Confirmed (at least 2 publishers) first with "N outlets", then single-source items muted with
  "via <publisher>"; 8 items, early items ordered by type: model, hardware, benchmark, dataset,
  technique, company, product, policy. Each item has one line (at most 140 characters, no provider
  call): the first digest-summary sentence of its articles that names it and has a launch or "is a"
  verb; a naming sentence when the novelty quote has fewer than 8 words; else the quote in quotation
  marks. "History: N complete days." while fewer than 30 complete days precede D.
- **Not New**: people and "other"; packaging variants of a known model (sizes, quantization,
  instruct/base); a name that does not look like a name (needs an uppercase letter or digit, or one
  hyphen/dot-joined token); a name already in an earlier published digest item; a name the digest
  text frames as not yet released (preview, beta, waitlist, coming soon and similar). A single
  common-word name is refused lexically only when its vendor appears in the same item. A new named
  version and a GA release after a preview are New. Refused items stay in the stored snapshot as
  `new_suppressed`, not in the API response.
- `variant of X` only for a specific earlier entity of the same type, never a family word (GPT,
  Claude, Gemini, Llama and similar).
- **Top stories**: clusters of articles about one event with at least 2 publishers, at most 5.
- **Rising / Cooling**: last 7 days against the previous 7 with a volume-adjusted expectation; needs
  two windows of at least 6 complete days each. Cooling only then, collapsed by default.
- **Spikes** (until Rising is usable): D's count against the mean of at least 3 complete trailing days
  with at least 10 digest items. A spike that duplicates a shown item (top story with at least half of
  its articles, a New item, an earlier spike of that company) folds into it as "spike: <names>"; a
  company spike with no story holding 2 of its articles is dropped. Kept spikes show the label of D's
  main story. Folded and dropped spikes are kept in the snapshot as `spikes_folded`; an empty card is
  hidden and its note moves to the status line.
- **Event chips**: stories per hard event type (`HARD_EVENTS`), the rest as "+N more"; display only.

**Brief**
- After the snapshots a paid run writes "In brief" for each target day: one call with the snapshot of
  D and the digest summaries of the referenced articles (at most 12,000 bytes; quiet day: every
  digest item, max 30). 3-5 sentences, 1-2 on a quiet day, each with numbered source links and the
  note "Written by AI from the linked articles; check the sources."
- Quiet day (fewer than 20 digest items or no multi-publisher story): an app-written opening line
  with the counts, then the brief, chips and only the cards that have items.
- The answer is checked mechanically: known article ids, an exact 5-40 word quote from a cited
  article, numbers and capitalized names present in the cited text, one sentence per story. An
  invalid answer gets one recovery attempt, then the day is stored `invalid` and shows no brief.
- Target days: the run's days with a usable snapshot, plus D-1 in a one-day run when D-1 has no
  current `ok` brief.

## Decisions

| Decision | Why |
| --- | --- |
| Scope = published digest of D, not all ingested articles | non-AI and non-admitted items never enter analytics (same scope as the digest) |
| One extraction call per article, separate from the digest summary call | digest prompts and replays stay pinned; one bad answer loses one article, not a batch |
| Entities derived from stored evidence by a pure function + overrides | same evidence gives same entities in any arrival or backfill order; fixes are replayable |
| Evidence survives retention and cleanup | "first seen" must not move forward when old articles are pruned |
| New = first seen in our corpus and presented as new by the article (model judgment, with quote) | New means newly announced, not merely new to our corpus (OD1) |
| Lexical safety nets after the model (name shape, earlier digest text, not-yet-released words) | prompt revisions stopped at `daily-signals-extract-5`; remaining errors are fixed in code at $0 |
| Thresholds are code constants recorded in every snapshot, no runtime override | a snapshot is reproducible; a change is a release with a `METHODOLOGY_VERSION` bump |
| Rising waits for two usable 7-day windows; spikes until then | a comparison needs enough complete days on both sides (OD3) |
| Brief in its own table keyed by input hash, not in the snapshot | snapshot hash stays pure; a recompute never drops a paid brief; same input never paid twice |
| Brief validated mechanically, meaning not checked | catches invented names, numbers and quotes without a second model call |
| Quiet-day opening line is a template, not model output | counts are our facts |
| Chips are display only | filtering the digest was deferred (OD4) |
| Signals run only after a successful publication; failure never changes the job result | the digest job must not depend on the signals block |

## Invariants

- Page loads and the API never call a provider; a missing or unreadable snapshot/brief gives
  `brief: null` or an unavailable state, never a 500.
- The digest, articles and weekly tables are never written by signals.
- `--max-usd` is the total for a run: extraction first, briefs get the remainder, at most
  `BRIEF_MAX_USD_PER_DAY` per target day.
- A brief failure never changes the extraction `state`, its results or the snapshots.
- Server and client renderers produce the same markup; change both together.
- Brief text is validated mechanically (ids, exact quote, numbers, capitalized names, one sentence
  per story); meaning is not checked.

# Code map

## Flow

```text
scripts/run_daily_digest_job.sh (02:00 UTC, after the digest)
  -> ai-news daily-signals                       src/app/cli/main.py: daily_signals
  -> run_signals                                 core/daily_signals.py
       _gate                    flag AINEWS_DAILY_SIGNALS_ENABLED + DS key; else state disabled/missing_provider_key
       repo.replace_membership  digest items of D -> articles (exact URL, then canonical hash)
       _extract_days            one DeepSeek call per in-scope article, via SignalsLedger
       repo.recompute_reports   reconcile entities, compute_snapshot per day, store if payload changed
       _briefs                  one brief call per target day (paid runs only), via a second ledger run
  -> JSON run report (stdout + data/daily-signals/runs/<run_id>.json)

GET /api/news/daily-signals?date=D               web/app.py: _read_daily_signals (DB reads only)
GET /?date=D                                     web/signals_view.py: render_signals (server)
                                                 web/digest.html: renderSignals (client, same markup)
```

## Modules

| File | Role | Pure |
| --- | --- | --- |
| `core/daily_signals.py` | Run orchestration, brief step, operator entity commands (`merge_entities`, `alias_entity`) | no |
| `core/daily_signals_extract.py` | Extraction prompt, request body, answer validation (`EXTRACTION_VERSION`) | yes |
| `core/daily_signals_entities.py` | Deterministic entity identity: keys, vendor classes, reconciliation, overrides | yes |
| `core/daily_signals_compute.py` | Snapshot of one day (`compute_snapshot`, `Thresholds`, `one_liner`, folding, quiet flag) | yes |
| `core/daily_signals_brief.py` | Brief packet, prompt, request body, validation rules 1-9, O1 review marker | yes |
| `storage/daily_signals.py` | `DailySignalRepo`: membership, extractions, evidence, entities, overrides, snapshots, briefs | no |
| `storage/daily_signals_ledger.py` | `SignalsLedger`: private SQLite of physical POSTs, replay, per-run caps, per-model prices | no |
| `web/signals_view.py` | Server HTML of the block; `quiet_line`, chips, D3 New list | yes |
| `web/models.py` | `DailySignalsResponse` and nested API models (only optional fields added after 006) | - |
| `web/digest.html` | `renderSignals`: client re-render on date change; must match `signals_view.py` | - |

## Tables

| Table | Holds | FK to `articles` |
| --- | --- | --- |
| `daily_signal_scope` | digest item -> article membership per day | cascade |
| `article_signals` | extraction per article, content hash, version | cascade |
| `signal_mentions` | evidence (mentions with quotes); survives retention | none |
| `ai_entities` | derived entities (rebuilt by reconciliation) | none |
| `ai_entity_overrides` | operator merges/aliases by stable selector keys | none |
| `daily_signal_reports` | one snapshot payload (JSON) per day, methodology version | none |
| `daily_signal_briefs` | one brief per day: status `ok`/`invalid`, input hash, model, payload | none |

Migrations: `b6d1f0a7c3e5` (006), `c3a8e5d27f14` (007); both skip objects that `create_all()` made.
Ledger and run reports live in `data/daily-signals/` (not in the database).

## Versions

| Constant | File | Bump when | After deploy |
| --- | --- | --- | --- |
| `EXTRACTION_VERSION` | `daily_signals_extract.py` | prompt or validation of extraction changes | paid re-extraction (backfill) |
| `METHODOLOGY_VERSION` | `daily_signals_compute.py` | thresholds or snapshot rules change | `--recompute-only --recompute-all` ($0) |
| `BRIEF_VERSION` | `daily_signals_brief.py` | brief prompt, packet or validation changes | brief backfill (paid) |

The brief `input_hash` covers packet, `BRIEF_VERSION` and model: an unchanged input is never paid
twice; a row with the same hash is reused even when `invalid`.

## Where to change what

| Change | Place | Also |
| --- | --- | --- |
| New/Top/Spike/Rising thresholds | `Thresholds` in `daily_signals_compute.py` | bump `METHODOLOGY_VERSION` |
| Family words for `variant of` | `FAMILY_STOPWORDS` in `daily_signals_compute.py` | methodology bump |
| Hard event types (chips, brief order) | `HARD_EVENTS` in `daily_signals_brief.py` | view uses the same tuple |
| Review marker (O1) | `REVIEW_TITLE`, `REVIEW_SHARE` in `daily_signals_brief.py` | `BRIEF_VERSION` bump |
| Brief prompt / rules | `BRIEF_PROMPT`, `parse_brief` in `daily_signals_brief.py` | `BRIEF_VERSION` bump, fixtures |
| Brief model / prices | setting `daily_signals_brief_model`; `BRIEF_PRICES` | unknown model -> `brief_model_unpriced`, no call |
| Extraction prompt | `daily_signals_extract.py` | `EXTRACTION_VERSION` bump (paid) |
| Entity merge rules | `daily_signals_entities.py` | operator overrides for single cases |
| Block markup | `signals_view.py` and `renderSignals` in `digest.html` | both |
| API fields | `web/models.py` | optional fields only |

## Tests

`tests/unit/test_daily_signals_*.py` (extract, entities, overrides, compute, brief, repo, migration,
ledger, run), `test_cli_daily_signals.py`, `test_web_daily_signals_api.py`, `test_web_public_digest.py`;
brief fixtures in `tests/fixtures/daily_signals/brief/`. Tests never call a provider
(`httpx.MockTransport`). PostgreSQL integration runs only with `AINEWS_TEST_POSTGRES_URL` (see
`docs/troubleshooting.md`).
