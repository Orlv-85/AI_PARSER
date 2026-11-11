# src/app - overview

Entry points: CLI `ai-news` (`cli/main.py`), web app (`web/app.py`, launched by `scripts/run_web.sh`).
Production jobs: `scripts/run_daily_fetch_job.sh`, `scripts/run_daily_digest_job.sh`.

## Packages

| Package | Role |
| --- | --- |
| `cli/` | Typer commands: sources, fetch, serve, top, search, prune, daily-publish, daily-signals (+ entities), period-signals, source candidates |
| `config/` | `settings.py` (env `AINEWS_*`), `sources.py` (`sources.yaml` loader) |
| `ingest/` | RSS/HTML fetching, page filtering, date evidence |
| `core/` | Rules and calculations. Shared: `models.py`, `categories.py`, `canonicalize.py`, `jev.py`, `provider_costs.py` (paid provider prices, dollar caps), `provider_errors.py` (payment journal stop errors), `canonical_json.py` (canonical JSON and its fingerprint). Packages: `ingestion/` (admission, scoring, dedup, `reject_policy.py` (conservative reject verdict)), `daily/` (rubric, provider requests, digest titles, daily signals calculations), `periodic/` (weekly and monthly signals calculations), `bulletin/` (builder, writer, world change), `world/` (world stream filter and reader), `sources/` (candidate fields and review rules) |
| `usecases/` | Runs that open sessions and call repositories and providers: `ingestion/pipeline/` (fetch cycle, Jev scorer with its journal), `daily/` (digest enrichment, daily signals run), `periodic/` (period runs), `bulletin/` (daily bulletin, day input, world change assessor with its journal, writer run), `archive/` (article archive capture), `sources/` (onboarding, validation), world stream jobs (collect, screen, text, report) |
| `storage/` | SQLAlchemy models (`models_sql.py`), repositories, Alembic migrations, ledgers and journals; `journal_files.py` (private atomic file writes) |
| `web/` | FastAPI app (`web/app.py`: auth middleware, router order), routers by area (`web/routes/`), API models (`web/models.py`), HTML templates |
| `observability/` | Logging setup |

## Layers

Imports go one way: `cli/`, `web/` -> `usecases/` -> `storage/` -> `core/` (spec
`specs/019-layer-boundaries/`).

- `core/` holds rules and calculations; it does not import `usecases/`, `storage/`, `cli/` or
  `web/`. A provider client in `core/` gets the payment journal from the use case that opens it;
  the journal's stop errors live in `core/provider_errors.py`. Tests:
  `test_core_imports_no_lower_or_upper_layer`.
- `usecases/` holds code that opens sessions and calls repositories and providers; it does not
  import `cli/` or `web/`. Tests: `test_use_cases_import_no_entry_point`.
- `storage/` may import `core/` types and constants it stores; it does not import `usecases/`,
  `cli/` or `web/`. Tests: `test_storage_imports_no_upper_layer`.
- `storage/` does not import the calculating functions of `core/` named in
  `tests/unit/test_layer_imports.py`; the use case calls them. One file is listed there as an
  exception and that list only shrinks (spec 019, T010). Tests:
  `test_storage_imports_calculations_only_in_listed_files`.
- The import scan sees imports inside functions and modules loaded by a literal name; relative
  imports are not used. Tests: `test_imports_package_sees_every_import_form`,
  `test_app_has_no_relative_imports`.
- `ingest/`, `config/` and `observability/` are not in the rule yet (spec 019, T015).

## Code docs

Feature docs live next to their main module and are checked by `scripts/check_code_docs.py`
(rule: AGENTS.md, "Feature Docs Next To Code").

| Feature | Doc |
| --- | --- |
| Provider payment journal | `storage/provider_journal.md` |
| Daily digest enrichment | `usecases/daily/enrichment.md` |
| Daily AI Signals (006, 007) | `usecases/daily/signals.md` |
| World change questions (018 item 1) | `core/bulletin/world_change.md` |
| Bulletin builder (018 item 2) | `core/bulletin/builder.md` |
| Bulletin writer (018 item 3) | `core/bulletin/writer.md` |
| Bulletin storage (018 item 4a) | `storage/bulletin_store.md` |
| Daily bulletin (018 item 4b) | `usecases/bulletin/daily.md` |
| Period AI Signals (017) | `core/periodic/signals_period.md` |
| Fetch pipeline (001, 002, admission) | `usecases/ingestion/pipeline.md` |
| Source onboarding (003, 011) | `usecases/sources/onboarding.md` |
| World news stream (018 item 5) | `core/world/world.md` |
| Article archive (016) | `usecases/archive/capture.md` |
| Web pages and static assets | `web/pages.md` |
