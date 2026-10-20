<!-- code-doc
module: src/app/core/daily_signals.py
covers:
  - src/app/core/daily_signals*.py
  - src/app/storage/daily_signals*.py
  - src/app/storage/migrations/versions/*daily_signal*.py
  - src/app/web/signals_view.py
-->
# Daily AI Signals - code map

Technical reference for 006 (signals) and 007 (brief). Operator commands, cost, rollback:
`docs/daily-signals.md`. Contracts: `specs/006-daily-ai-signals/`,
`specs/007-daily-signals-brief/`. Update this file in the same change as the code.

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

| Area | Tests |
| --- | --- |
| Extraction | `tests/unit/test_daily_signals_extract.py` |
| Entities, overrides | `test_daily_signals_entities.py`, `test_daily_signals_overrides.py` |
| Snapshot, one-liners, folding | `test_daily_signals_compute.py` |
| Brief | `test_daily_signals_brief.py` (fixtures `tests/fixtures/daily_signals/brief/`) |
| Repo, migration, ledger | `test_daily_signals_repo.py`, `test_daily_signals_migration.py`, `test_daily_signals_ledger.py` |
| Run, CLI | `test_daily_signals_run.py`, `test_cli_daily_signals.py` |
| API, page | `test_web_daily_signals_api.py`, `test_web_public_digest.py` |

Tests never call a provider (`httpx.MockTransport`). PostgreSQL integration runs only with
`AINEWS_TEST_POSTGRES_URL` (see `docs/troubleshooting.md`).
