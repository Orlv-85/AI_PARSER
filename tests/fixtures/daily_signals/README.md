# Daily AI Signals fixtures

`signals_2026-10-12.json` .. `signals_2026-10-16.json` are copied from the Phase A dry-run
(`tmp/daily-signals-dryrun/fixtures/`, see `specs/006-daily-ai-signals/dry-run.md`).

- Origin: the public digests of each day joined to the local SQLite articles; `article_id` is the local
  SQLite id at the time of the dry-run.
- Per article: digest key, title, URL, publisher, `published_at`, and the dry-run extraction fields
  (`event_type`, `novelty_claim`, `entities` with name, canonical, type, vendor, role, is_new).
- `prompt` is the dry-run prompt version: `v1` (batched, no novelty quotes) on 10-12, 10-14, 10-15 and
  10-16; `v2` on 10-13. These are not the production prompt (`daily-signals-extract-5`); tests use them
  for identity and clustering, and hand-written data for novelty rules.
- No article bodies are included.
